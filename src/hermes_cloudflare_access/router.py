"""Custom FastAPI router for the Cloudflare Access auth provider.

The provider's ``start_login`` redirects to
``/api/plugins/cloudflare_access/callback``. This route:

  1. Reads the Cf-Access-Jwt-Assertion request header (falls back to the
     CF_Authorization cookie — same JWT, two carriers).
  2. Validates the JWT against the team JWKS (cached 5 min in
     ``_JWKS`` in ``__init__.py``).
  3. Checks ``aud`` and ``iss`` match the provider's configured values.
  4. Mints a Hermes ``Session`` via the provider's own ``_mint_session``
     helper (re-used to keep the cookie / HMAC scheme identical to the
     basic / nous providers).
  5. Sets the session cookies (``hermes_session_at``, ``hermes_session_rt``,
     ``hermes_session_provider``) using the same helpers the standard
     ``/auth/callback`` route uses.
  6. 302-redirects to the ``next=`` target on the original request, or
     ``/`` if unset.

Failure modes:
  * No JWT in headers or cookies → 401 with a clear message telling the
    user to log in via the Cloudflare Access portal (which means the
    Access policy isn't actually in front of the dashboard, or the
    user is reaching the dashboard over an unauthenticated path).
  * JWT present but signature / aud / iss / exp invalid → 401 with the
    underlying reason logged at WARNING (operator-side signal).
  * Everything OK → cookies set, 302 to dashboard.
"""

from __future__ import annotations

import logging
import time
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import RedirectResponse
from hermes_cli.dashboard_auth import list_providers
from hermes_cli.dashboard_auth.cookies import (
    detect_https,
    set_session_cookies,
)
from hermes_cli.dashboard_auth.prefix import prefix_from_request

from . import verify_access_jwt

_log = logging.getLogger(__name__)

router = APIRouter()


# Header Cloudflare uses for the JWT; cookie name is the legacy form.
_HEADER_NAME = "cf-access-jwt-assertion"
_COOKIE_NAME = "CF_Authorization"


def _extract_jwt(request: Request) -> str:
    """Pull the JWT out of the request, header first then cookie."""
    h = request.headers.get(_HEADER_NAME, "").strip()
    if h:
        return h
    c = request.cookies.get(_COOKIE_NAME, "").strip()
    if c:
        return c
    return ""


def _safe_next(next_path: str) -> str:
    """Defence in depth: never redirect to an off-origin URL.

    Mirror of the same-origin check the standard /auth/callback applies.
    """
    if not next_path:
        return "/"
    if not next_path.startswith("/") or next_path.startswith("//"):
        return "/"
    return next_path


@router.get("/callback", name="cloudflare_access_callback")
async def callback(request: Request, next: str = "") -> Any:
    # 1. Find the registered provider.
    provider = None
    for p in list_providers():
        if getattr(p, "name", "") == "cloudflare_access":
            provider = p
            break
    if provider is None:
        raise HTTPException(
            status_code=503,
            detail="cloudflare_access provider not registered",
        )

    # 2. Pull the JWT from header / cookie.
    token = _extract_jwt(request)
    if not token:
        _log.warning(
            "dashboard-auth-cf-access: callback hit with no JWT in header "
            "or cookie — Cloudflare Access is not in front of the request, "
            "or the Access policy is misconfigured"
        )
        raise HTTPException(
            status_code=401,
            detail=(
                "No Cloudflare Access JWT found. Ensure the Access policy "
                "is in front of this hostname (browser should land here via "
                "the Access login interstitial, not directly)."
            ),
        )

    # 3. Verify signature, aud, iss, exp, nbf.
    try:
        claims = verify_access_jwt(
            token,
            team=provider._team,
            aud=provider._aud,  # type: ignore[attr-defined]
        )
    except Exception as exc:  # noqa: BLE001 — surface the reason
        _log.warning(
            "dashboard-auth-cf-access: JWT verification failed: %s",
            exc,
        )
        raise HTTPException(
            status_code=401,
            detail=f"Cloudflare Access JWT invalid: {exc}",
        )

    # 4. Mint a Session using the provider's own HMAC scheme.
    user_id = str(claims.get("sub", ""))
    email = str(claims.get("email", ""))
    if not user_id:
        raise HTTPException(
            status_code=401,
            detail="JWT missing 'sub' claim",
        )
    session = provider._mint_session(user_id=user_id, email=email)  # type: ignore[attr-defined]

    # 5. Compute cookie TTL + set session cookies (mirror standard callback).
    expires_in = max(60, session.expires_at - int(time.time()))
    target = _safe_next(next)
    response = RedirectResponse(url=target, status_code=302)
    set_session_cookies(
        response,
        access_token=session.access_token,
        refresh_token=session.refresh_token,
        access_token_expires_in=expires_in,
        use_https=detect_https(request),
        prefix=prefix_from_request(request),
        provider=session.provider,
    )
    _log.info(
        "dashboard-auth-cf-access: minted session for email=%s sub=%s -> %s",
        email,
        user_id,
        target,
    )
    return response
