"""FastAPI router for the cloudflare_access dashboard auth plugin.

Mounted by the dashboard plugin loader at /api/plugins/cloudflare_access/.
Reads the Cf-Access-Jwt-Assertion header (or CF_Authorization cookie) set
by Cloudflare's edge, verifies the JWT against the team JWKS, and mints
a Hermes session.

The actual auth provider implementation (DashboardAuthProvider subclass)
lives in the bundled dashboard_auth plugin at
``plugins/dashboard_auth/cloudflare_access/__init__.py``. This file
just re-exports the FastAPI router from there so the dashboard plugin
loader can import and mount it.

Try order:
  * The bundled path — works when the plugin ships inside the
    hermes-agent tree (the layout the README documents for manual installs).
  * The pip-installed package — works when the user installed via PyPI
    (this is the supported install path once the package is on PyPI).
"""

from __future__ import annotations

# Re-export the FastAPI router from whichever import path is available.
# The dashboard plugin loader runs inside Hermes's Python process so
# either path may resolve depending on the install layout.
try:
    from plugins.dashboard_auth.cloudflare_access.router import router  # noqa: F401
except ImportError:
    try:
        from hermes_cloudflare_access.router import router  # noqa: F401
    except ImportError:
        import logging
        _log = logging.getLogger(__name__)
        _log.warning(
            "cloudflare_access dashboard plugin: failed to import router "
            "from plugins.dashboard_auth.cloudflare_access.router or "
            "hermes_cloudflare_access.router; falling back to error stub",
        )
        from fastapi import APIRouter

        router = APIRouter()

        @router.get("/callback")
        async def _callback_stub():
            return {"error": "cloudflare_access plugin not properly installed"}