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
"""

from __future__ import annotations

# Re-export the FastAPI router from the bundled dashboard_auth plugin.
# The path is relative to the hermes-agent install dir; the dashboard
# plugin loader runs inside that Python process so this import works.
try:
    from plugins.dashboard_auth.cloudflare_access.router import router
except Exception as exc:  # noqa: BLE001
    import logging
    _log = logging.getLogger(__name__)
    _log.warning(
        "cloudflare_access dashboard plugin: failed to import router "
        "from plugins.dashboard_auth.cloudflare_access.router: %s", exc,
    )
    # Provide a stub so the dashboard plugin loader doesn't crash on import.
    from fastapi import APIRouter
    router = APIRouter()

    @router.get("/callback")
    async def _callback_stub():
        return {"error": "cloudflare_access plugin not properly installed"}
