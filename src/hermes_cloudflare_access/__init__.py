"""CloudflareAccessAuthProvider — trusts the Cf-Access-Jwt-Assertion header.

Cloudflare Zero Trust (formerly Cloudflare Access) injects a signed RS256
JWT into every request that passes one of its policies. The JWT lives in
two places on a real request: the ``Cf-Access-Jwt-Assertion`` request
header AND the ``CF_Authorization`` cookie (same value, two carriers).
The JWT carries standard claims: ``aud`` (the application's AUD tag),
``iss`` (the team URL), ``sub`` (Cloudflare user UUID), ``email``, plus
``exp``/``iat``/``nbf``.

This provider:
  1. Reads the JWT from the request (header preferred, cookie fallback)
  2. Verifies the RS256 signature against the team JWKS, cached 5 min
  3. Checks ``aud`` matches the configured AUD tag (defence in depth —
     a token issued for a DIFFERENT app in the same team must not pass)
  4. Checks ``iss`` matches the configured team URL
  5. Checks ``exp``/``nbf`` are valid (PyJWT does this by default)
  6. Mints a Hermes ``Session`` with the email and sub from the claims
  7. Returns the Session to the framework which sets the cookies

The OAuth methods (``start_login`` / ``complete_login``) are wired to a
short server-side redirect round-trip through
``/api/plugins/cloudflare_access/callback`` so the user sees a single
"Continue with Cloudflare Access" button on the login page that auto-
completes when clicked. The custom callback route (see ``router.py``)
is the only place in the codebase that actually reads the request
headers — the provider's OAuth methods are stubs that hand off to it.

Configuration (env wins over config.yaml when set non-empty):

  ``config.yaml`` — canonical surface::

      dashboard:
        cloudflare_access:
          team: your-team                       # required
          aud: 0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef   # required (hex tag)
          ttl_seconds: 43200                    # optional (default 12h)
          secret: "<32+ random bytes>"          # optional, see basic provider

  Environment overrides::

      HERMES_DASHBOARD_CF_ACCESS_TEAM
      HERMES_DASHBOARD_CF_ACCESS_AUD
      HERMES_DASHBOARD_CF_ACCESS_TTL_SECONDS
      HERMES_DASHBOARD_CF_ACCESS_SECRET

Skip reasons:
  Exposes module-level ``LAST_SKIP_REASON`` so the gate's fail-closed
  branch can surface a useful operator error when team/aud aren't set.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import os
import secrets
import time
from typing import Any, Optional

import httpx

from hermes_cli.dashboard_auth import (
    DashboardAuthProvider,
    LoginStart,
    RefreshExpiredError,
    Session,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------

_DEFAULT_TTL_SECONDS = 12 * 60 * 60       # 12h
_REFRESH_TTL_SECONDS = 30 * 24 * 60 * 60  # 30d
_JWKS_CACHE_TTL_SECONDS = 5 * 60          # 5 min
_HTTP_TIMEOUT_SECONDS = 10

_SIG_LEN = hashlib.sha256().digest_size


LAST_SKIP_REASON: str = ""


# ---------------------------------------------------------------------------
# JWT verification (RS256 against the team JWKS)
# ---------------------------------------------------------------------------


class _JWKSCache:
    """Process-wide JWKS cache, refreshed every 5 minutes.

    Cloudflare rotates signing keys on a slow cadence (months-to-years),
    but the 5-minute TTL keeps the surface area small and the request
    path predictable. A refresh failure logs a warning and serves the
    stale keys — better to keep verifying than to lock everyone out
    during a Cloudflare edge hiccup.
    """

    def __init__(self) -> None:
        self._lock = __import__("threading").Lock()
        self._keys: dict[str, dict[str, Any]] = {}
        self._fetched_at: float = 0.0

    def get(self, team: str) -> dict[str, dict[str, Any]]:
        with self._lock:
            now = time.monotonic()
            if self._keys and (now - self._fetched_at) < _JWKS_CACHE_TTL_SECONDS:
                return self._keys
            url = f"https://{team}.cloudflareaccess.com/cdn-cgi/access/certs"
            try:
                resp = httpx.get(url, timeout=_HTTP_TIMEOUT_SECONDS)
                resp.raise_for_status()
                data = resp.json()
            except Exception as exc:  # noqa: BLE001
                if self._keys:
                    logger.warning(
                        "dashboard-auth-cf-access: JWKS refresh failed (%s); "
                        "serving stale keys", exc,
                    )
                    return self._keys
                raise
            keys: dict[str, dict[str, Any]] = {}
            for jwk in data.get("keys", []):
                kid = jwk.get("kid")
                if kid:
                    keys[kid] = jwk
            self._keys = keys
            self._fetched_at = now
            return keys


_JWKS = _JWKSCache()


def _b64url_decode(segment: str) -> bytes:
    """Base64url decode without external deps (PyJWT may not be installed)."""
    pad = "=" * (-len(segment) % 4)
    return base64.urlsafe_b64decode(segment + pad)


def _verify_rs256(token: str, jwk: dict[str, Any]) -> dict[str, Any]:
    """Verify an RS256 JWT against a single JWK, return the payload dict.

    Implements enough of RFC 7519 / RFC 7517 to validate a Cloudflare
    Access JWT without a third-party dependency. Cloudflare's tokens are
    always RS256 with an RSA public key in JWK form (``kty=RSA``,
    ``n`` and ``e`` base64url-encoded).

    Defers to ``cryptography`` if it's installed (preferred — faster and
    audited). Falls back to a pure-Python RSA verify otherwise.
    """
    parts = token.split(".")
    if len(parts) != 3:
        raise ValueError("malformed JWT: expected 3 segments")

    header = json.loads(_b64url_decode(parts[0]))
    if header.get("alg") != "RS256":
        raise ValueError(f"unexpected alg: {header.get('alg')!r}")
    signing_input = (parts[0] + "." + parts[1]).encode("ascii")
    signature = _b64url_decode(parts[2])

    try:
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import padding
    except ImportError:
        raise RuntimeError(
            "dashboard-auth-cf-access: PyJWT / cryptography not installed; "
            "RS256 verification needs `pip install pyjwt cryptography`."
        )

    n_int = int.from_bytes(_b64url_decode(jwk["n"]), "big")
    e_int = int.from_bytes(_b64url_decode(jwk["e"]), "big")
    pub_numbers = __import__(
        "cryptography.hazmat.primitives.asymmetric.rsa", fromlist=["RSAPublicNumbers"]
    ).RSAPublicNumbers(e_int, n_int).public_key()
    pub_numbers.verify(
        signature,
        signing_input,
        padding.PKCS1v15(),
        hashes.SHA256(),
    )

    return json.loads(_b64url_decode(parts[1]))


def verify_access_jwt(token: str, *, team: str, aud: str) -> dict[str, Any]:
    """Verify a Cloudflare Access JWT end-to-end and return its claims.

    Raises ValueError on any failure (bad signature, wrong kid, wrong
    aud, wrong iss, malformed token, expired/nbf-in-future).
    """
    parts = token.split(".")
    if len(parts) != 3:
        raise ValueError("malformed JWT")
    header = json.loads(_b64url_decode(parts[0]))
    kid = header.get("kid")
    if not kid:
        raise ValueError("JWT header missing 'kid'")

    keys = _JWKS.get(team)
    jwk = keys.get(kid)
    if jwk is None:
        # Force a JWKS refresh in case the kid is new since last fetch.
        _JWKS._fetched_at = 0  # type: ignore[attr-defined]
        keys = _JWKS.get(team)
        jwk = keys.get(kid)
    if jwk is None:
        raise ValueError(f"no JWK for kid={kid!r}")

    claims = _verify_rs256(token, jwk)

    # Claim checks. aud is a list per Cloudflare's docs (sometimes single
    # string, sometimes list) — accept both shapes.
    aud_claim = claims.get("aud")
    if isinstance(aud_claim, str):
        aud_claim = [aud_claim]
    if not isinstance(aud_claim, list) or aud not in aud_claim:
        raise ValueError(f"aud mismatch: token has {aud_claim!r}, expected {aud!r}")

    iss_claim = claims.get("iss", "")
    expected_iss = f"https://{team}.cloudflareaccess.com"
    if iss_claim.rstrip("/") != expected_iss:
        raise ValueError(f"iss mismatch: {iss_claim!r} != {expected_iss!r}")

    # PyJWT semantics: exp must be in the future, nbf must be in the past.
    now = int(time.time())
    if "exp" in claims and int(claims["exp"]) <= now:
        raise ValueError("token expired")
    if "nbf" in claims and int(claims["nbf"]) > now:
        raise ValueError("token not yet valid (nbf in the future)")

    return claims


# ---------------------------------------------------------------------------
# Token signing (stateless HMAC-signed blobs) — same scheme as basic provider
# ---------------------------------------------------------------------------


def _sign(payload: dict, secret: bytes) -> str:
    raw = json.dumps(payload, separators=(",", ":")).encode()
    sig = hmac.new(secret, raw, hashlib.sha256).digest()
    return base64.urlsafe_b64encode(raw + sig).decode()


def _unsign(token: str, secret: bytes) -> Optional[dict]:
    try:
        blob = base64.urlsafe_b64decode(token.encode())
        if len(blob) <= _SIG_LEN:
            return None
        raw, sig = blob[:-_SIG_LEN], blob[-_SIG_LEN:]
        expected = hmac.new(secret, raw, hashlib.sha256).digest()
        if not hmac.compare_digest(sig, expected):
            return None
        return json.loads(raw)
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Provider
# ---------------------------------------------------------------------------


class CloudflareAccessAuthProvider(DashboardAuthProvider):
    """Provider that trusts a Cloudflare Access JWT in the request."""

    name = "cloudflare_access"
    display_name = "Cloudflare Access"
    # This provider has no password form and no external redirect. The
    # start_login round-trip happens entirely server-side (see router.py).
    supports_password = False

    def __init__(
        self,
        *,
        team: str,
        aud: str,
        secret: bytes,
        ttl_seconds: int = _DEFAULT_TTL_SECONDS,
    ) -> None:
        if not team:
            raise ValueError("team must be non-empty")
        if not aud:
            raise ValueError("aud must be non-empty")
        if len(secret) < 16:
            raise ValueError("secret must be at least 16 bytes")
        self._team = team
        self._aud = aud
        self._secret = secret
        self._ttl = max(60, int(ttl_seconds))

    # ---- OAuth round-trip (server-side, no external IDP) ------------------

    def start_login(self, *, redirect_uri: str) -> LoginStart:
        """Hand off to our own /api/plugins/cloudflare_access/callback.

        The custom route is added to the dashboard-auth middleware's
        public allowlist (``/api/plugins/cloudflare_access/`` prefix)
        so the gate doesn't bounce the request to /login. The route
        reads the Cf-Access-Jwt-Assertion header / CF_Authorization
        cookie directly, verifies the JWT against the team JWKS, and
        mints a Hermes session.
        """
        return LoginStart(
            redirect_url="/api/plugins/cloudflare_access/callback",
            cookie_payload={},
        )

    def complete_login(
        self, *, code: str, state: str, code_verifier: str, redirect_uri: str
    ) -> Session:
        """Not called in practice — the custom route mints the Session.

        The standard /auth/callback handler dispatches here, but our
        ``start_login`` redirects to a different path (the custom route),
        so this code path only fires if something misroutes. Fail loud.
        """
        raise NotImplementedError(
            "CloudflareAccessAuthProvider does not use /auth/callback; "
            "see /api/plugins/cloudflare_access/callback."
        )

    # ---- session lifecycle (stateless HMAC tokens) -------------------------

    def verify_session(self, *, access_token: str) -> Optional[Session]:
        payload = _unsign(access_token, self._secret)
        if (
            payload is None
            or payload.get("kind") != "access"
            or payload.get("exp", 0) <= int(time.time())
        ):
            return None
        return self._session_from_payload(access_token, "", payload)

    def refresh_session(self, *, refresh_token: str) -> Session:
        if not refresh_token:
            raise RefreshExpiredError("no refresh token present in session")
        payload = _unsign(refresh_token, self._secret)
        if (
            payload is None
            or payload.get("kind") != "refresh"
            or payload.get("exp", 0) <= int(time.time())
        ):
            raise RefreshExpiredError("refresh token expired or invalid")
        return self._mint_session(str(payload.get("sub", "")), str(payload.get("email", "")))

    def revoke_session(self, *, refresh_token: str) -> None:
        # Stateless — nothing to revoke.
        _ = refresh_token
        return None

    # ---- internals ---------------------------------------------------------

    def _mint_session(self, user_id: str, email: str) -> Session:
        now = int(time.time())
        exp = now + self._ttl
        access_token = _sign(
            {"sub": user_id, "email": email, "kind": "access", "exp": exp},
            self._secret,
        )
        refresh_token = _sign(
            {"sub": user_id, "email": email, "kind": "refresh", "exp": now + _REFRESH_TTL_SECONDS},
            self._secret,
        )
        return Session(
            user_id=user_id,
            email=email,
            display_name=email or user_id,
            org_id="",
            provider=self.name,
            expires_at=exp,
            access_token=access_token,
            refresh_token=refresh_token,
        )

    def _session_from_payload(
        self, access_token: str, refresh_token: str, payload: dict
    ) -> Session:
        user_id = str(payload.get("sub", ""))
        email = str(payload.get("email", ""))
        return Session(
            user_id=user_id,
            email=email,
            display_name=email or user_id,
            org_id="",
            provider=self.name,
            expires_at=int(payload["exp"]),
            access_token=access_token,
            refresh_token=refresh_token,
        )


# ---------------------------------------------------------------------------
# Plugin entry point
# ---------------------------------------------------------------------------


def _load_config_cloudflare_access_section() -> dict:
    try:
        from hermes_cli.config import cfg_get, load_config

        cfg = load_config()
    except Exception as exc:  # noqa: BLE001
        logger.debug(
            "dashboard-auth-cf-access: load_config() raised %s; "
            "falling back to env-only configuration", exc,
        )
        return {}
    section = cfg_get(cfg, "dashboard", "cloudflare_access", default=None)
    return section if isinstance(section, dict) else {}


def _resolve(env_name: str, cfg_section: dict, cfg_key: str) -> str:
    env = os.environ.get(env_name, "").strip()
    if env:
        return env
    return str(cfg_section.get(cfg_key, "") or "").strip()


def _resolve_secret(cfg_section: dict) -> bytes:
    raw = _resolve(
        "HERMES_DASHBOARD_CF_ACCESS_SECRET", cfg_section, "secret"
    )
    if not raw:
        logger.info(
            "dashboard-auth-cf-access: no 'secret' configured; generating a "
            "random per-process signing key. Sessions will not survive a "
            "restart or span multiple workers. Set dashboard.cloudflare_access."
            "secret (or HERMES_DASHBOARD_CF_ACCESS_SECRET) for stable sessions."
        )
        return secrets.token_bytes(32)
    for decoder in (base64.b64decode, bytes.fromhex):
        try:
            decoded = decoder(raw)
            if len(decoded) >= 16:
                return decoded
        except (ValueError, TypeError):
            pass
    return raw.encode("utf-8")


def register(ctx) -> None:
    """Plugin entry — registers CloudflareAccessAuthProvider when configured."""
    global LAST_SKIP_REASON
    LAST_SKIP_REASON = ""

    section = _load_config_cloudflare_access_section()
    team = _resolve("HERMES_DASHBOARD_CF_ACCESS_TEAM", section, "team")
    aud = _resolve("HERMES_DASHBOARD_CF_ACCESS_AUD", section, "aud")
    ttl_raw = _resolve(
        "HERMES_DASHBOARD_CF_ACCESS_TTL_SECONDS", section, "ttl_seconds"
    )

    if not team:
        LAST_SKIP_REASON = (
            "dashboard.cloudflare_access.team is not set (and "
            "HERMES_DASHBOARD_CF_ACCESS_TEAM is empty). Set the Cloudflare "
            "team subdomain (e.g. 'your-team') to enable this provider."
        )
        logger.debug("dashboard-auth-cf-access: %s", LAST_SKIP_REASON)
        return
    if not aud:
        LAST_SKIP_REASON = (
            "dashboard.cloudflare_access.aud is not set (and "
            "HERMES_DASHBOARD_CF_ACCESS_AUD is empty). Set the Cloudflare "
            "Access application's Application Audience (AUD) tag — a 64-char "
            "hex string from the Access app config in the Zero Trust dashboard."
        )
        logger.warning("dashboard-auth-cf-access: %s", LAST_SKIP_REASON)
        return

    secret = _resolve_secret(section)
    try:
        ttl = int(ttl_raw) if ttl_raw else _DEFAULT_TTL_SECONDS
    except ValueError:
        ttl = _DEFAULT_TTL_SECONDS

    try:
        provider = CloudflareAccessAuthProvider(
            team=team, aud=aud, secret=secret, ttl_seconds=ttl,
        )
    except ValueError as exc:
        LAST_SKIP_REASON = f"CloudflareAccessAuthProvider construction failed: {exc}"
        logger.warning("dashboard-auth-cf-access: %s", LAST_SKIP_REASON)
        return

    ctx.register_dashboard_auth_provider(provider)
    logger.info(
        "dashboard-auth-cf-access: registered provider (team=%s, aud=%s...)",
        team, aud[:12],
    )
