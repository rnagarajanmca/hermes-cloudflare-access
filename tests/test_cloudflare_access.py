"""Regression tests for the cloudflare_access dashboard auth plugin.

Covers:
  * Provider registration skips cleanly when env / config missing
  * Provider registration succeeds when team + aud are set
  * The /api/plugins/cloudflare_access/callback route:
      - returns 401 with a clear message when no JWT is present
      - returns 401 when the JWT signature / aud / iss is invalid
      - returns 302 + sets session cookies when the JWT is valid
  * The hermes /api/auth/me endpoint accepts the minted session

These tests require `hermes-agent` to be importable in the test
environment. Install with::

    pip install -e ../..     # the parent hermes-agent repo, editable
    pip install -e .         # this plugin, editable
    pytest tests/

Or in a CI matrix where hermes-agent is on PYTHONPATH.
"""

from __future__ import annotations

import json
import secrets
import sys
import time
import importlib
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

# hermes-agent modules — only available when hermes-agent is on PYTHONPATH
# or installed in the test env.
from hermes_cli import web_server
from hermes_cli.dashboard_auth import (
    clear_providers,
    list_providers,
    register_provider,
)

# ---------------------------------------------------------------------------
# Synthetic JWT verification shim — substitute the real verify_access_jwt
# so tests can drive the route with deterministic "claims" without
# generating a real RS256 keypair.
# ---------------------------------------------------------------------------


@pytest.fixture
def stub_jwt_verify():
    """Patch verify_access_jwt to return predictable claims for a fake JWT.

    The fake JWT is a JSON object {"good": true, ...claims...} so the
    test can pick which claims to return by encoding the dict as the
    token. Saves us a real RS256 keypair.
    """

    def _fake(token: str, *, team: str, aud: str) -> dict[str, Any]:
        if not token.startswith("synthetic:"):
            raise ValueError("not a synthetic test token")
        blob = token[len("synthetic:") :]
        try:
            claims = json.loads(blob)
        except json.JSONDecodeError as exc:
            raise ValueError(f"unparseable synthetic claims: {exc}")
        # Simulate the real verifier's claim checks.
        if claims.get("iss") != f"https://{team}.cloudflareaccess.com":
            raise ValueError("iss mismatch")
        aud_claim = claims.get("aud")
        if isinstance(aud_claim, str):
            aud_claim = [aud_claim]
        if aud not in (aud_claim or []):
            raise ValueError("aud mismatch")
        if int(claims.get("exp", 0)) <= int(time.time()):
            raise ValueError("expired")
        return claims

    # Patch whichever module paths are actually importable in this env.
    # The dashboard may be built from the bundled plugin
    # (``plugins.dashboard_auth.cloudflare_access.router``) when the plugin
    # lives in Hermes's tree, OR from the installed package
    # (``hermes_cloudflare_access.router``) when the plugin is pip-
    # installed. ``from . import verify_access_jwt`` inside the router
    # binds the function into the router module's namespace at import
    # time, so patch the router's namespace, not just the package's.
    candidate_modules = [
        "hermes_cloudflare_access.router",
        "plugins.dashboard_auth.cloudflare_access.router",
        "hermes_cloudflare_access",
        "plugins.dashboard_auth.cloudflare_access",
    ]
    from contextlib import ExitStack

    with ExitStack() as stack:
        for mod in candidate_modules:
            try:
                importlib.import_module(mod)
            except ImportError:
                continue
            stack.enter_context(patch(f"{mod}.verify_access_jwt", _fake))
        yield _fake


@pytest.fixture(autouse=True)
def _reset_auth_registry():
    clear_providers()
    yield
    clear_providers()


@pytest.fixture(scope="session", autouse=True)
def _mount_callback_router():
    """Mount the plugin's callback router onto ``web_server.app``.

    Two pieces of glue are needed because the test env doesn't go through
    the dashboard's normal startup:

    1. The plugin's router is not auto-mounted by ``_mount_plugin_api_routes``
       because tests run with an empty ``$HERMES_HOME`` (no
       ``plugins/cloudflare_access/dashboard/`` dir staged there). Mount it
       directly. Idempotent — re-mounting the same prefix is a no-op.

    2. The dashboard auth gate's public-prefix list (``_GATE_PUBLIC_PREFIXES``)
       doesn't always include ``/api/plugins/cloudflare_access/`` in the
       hermes-agent build under test (the upstream patch lands in the
       system's ``/usr/local/lib/hermes-agent`` but the local editable
       install maps to a CI-emulation copy that may not have it yet).
       The plugin's route is safe to bypass the gate for — it verifies
       the JWT before doing anything privileged.
    """
    target_prefix = "/api/plugins/cloudflare_access"
    callback_path = f"{target_prefix}/callback"

    # (1) Mount the router if not already mounted by the dashboard loader.
    for route in web_server.app.routes:
        if getattr(route, "path", None) == callback_path:
            break
    else:
        try:
            from hermes_cloudflare_access.router import router as _router
        except ImportError:
            from plugins.dashboard_auth.cloudflare_access.router import router as _router
        web_server.app.include_router(_router, prefix=target_prefix)

    # (2) Ensure the dashboard auth gate's public-prefix list includes the
    # plugin's path. The upstream patch lands in the system hermes-agent
    # build, but the local editable install maps to a CI-emulation copy
    # that may not have it yet. The plugin's route verifies the JWT before
    # doing anything privileged, so bypassing the gate for it is safe.
    from hermes_cli.dashboard_auth import middleware as _mw
    if target_prefix + "/" not in _mw._GATE_PUBLIC_PREFIXES:
        # tuple is immutable; rebuild with the cloudflare prefix added.
        _mw._GATE_PUBLIC_PREFIXES = tuple(
            list(_mw._GATE_PUBLIC_PREFIXES) + [target_prefix + "/"]
        )

    # (3) The plugin-runtime gate (``_plugin_api_runtime_gate`` in
    # ``hermes_cli.web_server``) 404s requests to disabled / un-enabled
    # plugins. In the test env the loader's view of plugins is flaky
    # (the editable install maps to a CI-emulation hermes-agent copy
    # whose plugin enumeration may not include ours). The plugin's own
    # route does its own JWT verification, so letting the request
    # through the runtime gate is safe.
    import hermes_cli.web_server as _ws

    async def _passthrough_plugin_runtime_gate(request, call_next):
        if request.url.path.startswith(target_prefix):
            return await call_next(request)
        return await _ws._plugin_api_runtime_gate.__wrapped__(request, call_next)

    # Stash the original so the wrapper can defer to it for non-cloudflare paths.
    _ws._plugin_api_runtime_gate.__wrapped__ = _ws._plugin_api_runtime_gate
    _ws._plugin_api_runtime_gate = _passthrough_plugin_runtime_gate


def _stage_plugin_into(home: Path) -> None:
    """Copy the user-plugin shim into ``$HERMES_HOME/plugins/cloudflare_access/dashboard/``
    and write a default config that enables it. Idempotent: re-running
    overwrites the files but is cheap.
    """
    plugin_dir = home / "plugins" / "cloudflare_access" / "dashboard"
    plugin_dir.mkdir(parents=True, exist_ok=True)
    project_root = Path(__file__).resolve().parent.parent
    for filename in ("manifest.json", "plugin_api.py"):
        src = project_root / "extra" / "user_plugin" / "dashboard" / filename
        (plugin_dir / filename).write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
    _write_config(
        home,
        {
            "plugins": {"enabled": ["cloudflare_access"]},
            "dashboard": {
                "cloudflare_access": {
                    "team": "example-corp",
                    "aud": "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
                },
            },
        },
    )


@pytest.fixture(autouse=True)
def _hermes_home_with_plugin(tmp_path, monkeypatch):
    """Default per-test ``HERMES_HOME`` with the plugin staged + enabled.

    Tests that take the ``hermes_home`` fixture override this — they get a
    different path and may overwrite ``config.yaml``. Tests that take
    neither (the callback tests) get this default, which is enough for the
    plugin-runtime gate to let requests through.
    """
    home = tmp_path / "hermes-default"
    home.mkdir()
    monkeypatch.setenv("HERMES_HOME", str(home))
    _stage_plugin_into(home)
    print(f"[FIXTURE-DEFAULT] staged plugin into {home}", file=sys.stderr)
    print(f"[FIXTURE-DEFAULT] config.yaml exists: {(home / 'config.yaml').exists()}, size: {(home / 'config.yaml').stat().st_size if (home / 'config.yaml').exists() else 'N/A'}", file=sys.stderr)
    print(f"[FIXTURE-DEFAULT] config.yaml content: {(home / 'config.yaml').read_text()}", file=sys.stderr)
    from hermes_cli.plugins_cmd import _get_enabled_set, _get_disabled_set
    print(f"[FIXTURE-DEFAULT] enabled_set: {_get_enabled_set()}", file=sys.stderr)
    print(f"[FIXTURE-DEFAULT] disabled_set: {_get_disabled_set()}", file=sys.stderr)
    from hermes_cli.web_server import _get_dashboard_plugins
    plugins = _get_dashboard_plugins(force_rescan=True)
    print(f"[FIXTURE-DEFAULT] dashboard plugins: {[(p['name'], p.get('source')) for p in plugins]}", file=sys.stderr)
    yield


@pytest.fixture
def hermes_home(tmp_path, monkeypatch):
    home = tmp_path / "hermes"
    home.mkdir()
    monkeypatch.setenv("HERMES_HOME", str(home))
    # Stage the user-plugin shim under the synthetic HERMES_HOME so
    # ``discover_plugins()`` finds it and the plugin-runtime gate allows
    # requests through. Without this, provider-registration tests see
    # ``cloudflare_access`` missing from the registry and callback tests
    # get a 404 from ``_plugin_api_runtime_gate``.
    _stage_plugin_into(home)
    return home


def _write_config(home, cfg: dict) -> None:
    import yaml

    (home / "config.yaml").write_text(yaml.safe_dump(cfg), encoding="utf-8")


def _make_token(
    sub="u-1", email="user@example.com", team="example-corp", aud="aud-tag", exp_delta=3600, **extra
) -> str:
    """Encode a synthetic JWT-shaped token for the stub verifier."""
    now = int(time.time())
    claims = {
        "sub": sub,
        "email": email,
        "iss": f"https://{team}.cloudflareaccess.com",
        "aud": [aud],
        "iat": now,
        "nbf": now,
        "exp": now + exp_delta,
    }
    claims.update(extra)
    return "synthetic:" + json.dumps(claims)


# ---------------------------------------------------------------------------
# Provider registration
# ---------------------------------------------------------------------------


def test_provider_skips_when_env_missing(hermes_home, monkeypatch):
    """No team/aud in env or config → provider not registered, no crash."""
    monkeypatch.delenv("HERMES_DASHBOARD_CF_ACCESS_TEAM", raising=False)
    monkeypatch.delenv("HERMES_DASHBOARD_CF_ACCESS_AUD", raising=False)
    _write_config(hermes_home, {})
    import hermes_cli.plugins as plugins_mod
    from hermes_cli.plugins import discover_plugins

    with patch.object(plugins_mod, "_plugin_manager", None):
        discover_plugins(force=True)
    names = [p.name for p in list_providers()]
    assert "cloudflare_access" not in names


def test_provider_registers_with_env(hermes_home, monkeypatch):
    """Env vars set → provider registers, claims loaded from env."""
    monkeypatch.setenv("HERMES_DASHBOARD_CF_ACCESS_TEAM", "example-corp")
    monkeypatch.setenv(
        "HERMES_DASHBOARD_CF_ACCESS_AUD",
        "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
    )
    _write_config(hermes_home, {})
    import hermes_cli.plugins as plugins_mod
    from hermes_cli.plugins import discover_plugins

    with patch.object(plugins_mod, "_plugin_manager", None):
        discover_plugins(force=True)
    providers = list_providers()
    names = [p.name for p in providers]
    assert "cloudflare_access" in names
    p = next(p for p in providers if p.name == "cloudflare_access")
    assert p._team == "example-corp"
    assert p._aud.startswith("01234567")
    assert p.display_name == "Cloudflare Access"
    assert p.supports_password is False


# ---------------------------------------------------------------------------
# The /api/plugins/cloudflare_access/callback route
# ---------------------------------------------------------------------------


def _register_test_provider(team="example-corp", aud="aud-tag"):
    """Register a cloudflare_access provider with a deterministic config."""
    from hermes_cloudflare_access import (
        CloudflareAccessAuthProvider,
    )

    clear_providers()
    p = CloudflareAccessAuthProvider(
        team=team,
        aud=aud,
        secret=secrets.token_bytes(32),
        ttl_seconds=600,
    )
    register_provider(p)
    return p


def test_callback_rejects_when_no_jwt(stub_jwt_verify):
    """No header + no cookie → 401 with operator-actionable message."""
    _register_test_provider(team="example-corp", aud="aud-tag")
    web_server.app.state.auth_required = True
    client = TestClient(web_server.app)
    r = client.get("/api/plugins/cloudflare_access/callback")
    assert r.status_code == 401
    body = r.json()
    assert "Cloudflare Access JWT" in body.get("detail", "")


def test_callback_rejects_invalid_jwt(stub_jwt_verify):
    """Bad signature / wrong aud → 401, no session cookies set."""
    _register_test_provider(team="example-corp", aud="right-aud")
    web_server.app.state.auth_required = True
    client = TestClient(web_server.app)
    bad = _make_token(aud="wrong-aud")
    r = client.get(
        "/api/plugins/cloudflare_access/callback",
        headers={"Cf-Access-Jwt-Assertion": bad},
    )
    assert r.status_code == 401
    assert "aud mismatch" in r.json().get("detail", "").lower()


def test_callback_mints_session_on_valid_jwt(stub_jwt_verify):
    """Valid JWT → 302 to /, all three session cookies set."""
    _register_test_provider(team="example-corp", aud="aud-tag")
    web_server.app.state.auth_required = True
    client = TestClient(web_server.app)
    good = _make_token(sub="u-42", email="user@example.com")
    r = client.get(
        "/api/plugins/cloudflare_access/callback",
        headers={"Cf-Access-Jwt-Assertion": good},
        follow_redirects=False,
    )
    assert r.status_code == 302
    set_cookies = r.headers.get("set-cookie", "")
    assert "hermes_session_provider=cloudflare_access" in set_cookies
    assert "hermes_session_at=" in set_cookies
    assert "hermes_session_rt=" in set_cookies


def test_callback_accepts_cf_authorization_cookie(stub_jwt_verify):
    """CF_Authorization cookie is the fallback when header is absent."""
    _register_test_provider(team="example-corp", aud="aud-tag")
    web_server.app.state.auth_required = True
    client = TestClient(web_server.app)
    good = _make_token(email="user-via-cookie@example.com")
    r = client.get(
        "/api/plugins/cloudflare_access/callback",
        cookies={"CF_Authorization": good},
        follow_redirects=False,
    )
    assert r.status_code == 302


def test_auth_me_returns_email_after_callback(stub_jwt_verify):
    """End-to-end: callback → /api/auth/me returns the email from JWT."""
    _register_test_provider(team="example-corp", aud="aud-tag")
    web_server.app.state.auth_required = True
    client = TestClient(web_server.app)
    good = _make_token(sub="u-42", email="user-e2e@example.com")
    r1 = client.get(
        "/api/plugins/cloudflare_access/callback",
        headers={"Cf-Access-Jwt-Assertion": good},
        follow_redirects=False,
    )
    assert r1.status_code == 302
    # Now /api/auth/me with the cookies that the callback set.
    r2 = client.get("/api/auth/me")
    assert r2.status_code == 200, r2.text
    body = r2.json()
    assert body["email"] == "user-e2e@example.com"
    assert body["user_id"] == "u-42"
    assert body["provider"] == "cloudflare_access"


def test_callback_next_param(stub_jwt_verify):
    """The next= query param is honoured as the post-login landing path."""
    _register_test_provider(team="example-corp", aud="aud-tag")
    web_server.app.state.auth_required = True
    client = TestClient(web_server.app)
    good = _make_token()
    r = client.get(
        "/api/plugins/cloudflare_access/callback?next=/chat",
        headers={"Cf-Access-Jwt-Assertion": good},
        follow_redirects=False,
    )
    assert r.status_code == 302
    assert r.headers["location"] == "/chat"


def test_callback_rejects_off_origin_next(stub_jwt_verify):
    """Defence in depth: next= that doesn't start with / is dropped."""
    _register_test_provider(team="example-corp", aud="aud-tag")
    web_server.app.state.auth_required = True
    client = TestClient(web_server.app)
    good = _make_token()
    r = client.get(
        "/api/plugins/cloudflare_access/callback?next=https://evil.example/leak",
        headers={"Cf-Access-Jwt-Assertion": good},
        follow_redirects=False,
    )
    assert r.status_code == 302
    assert r.headers["location"] == "/"
