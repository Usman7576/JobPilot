from __future__ import annotations

import secrets
import uuid

from fastapi import APIRouter, Request, Response, status
from fastapi.responses import RedirectResponse

from app.core import security
from app.core.config import get_settings
from app.core.deps import CurrentUser, DbSession
from app.core.errors import AppError
from app.core.logging import get_logger
from app.core.ratelimit import limiter
from app.integrations import gmail, google_oauth
from app.models.enums import IntegrationProvider
from app.schemas.integration import ConnectOut, IntegrationsOut
from app.services import integration_service

router = APIRouter(prefix="/integrations", tags=["integrations"])
log = get_logger(__name__)
STATE_COOKIE = "g_connect_state"
STATE_PATH = "/api/v1/integrations"


class GoogleNotConfigured(AppError):
    status_code, code, title = 409, "google_not_configured", "Google isn't set up"


@router.get("")
async def list_integrations(user: CurrentUser, db: DbSession) -> IntegrationsOut:
    return await integration_service.overview(db, user)


@router.get("/gmail/connect")
@limiter.limit("10/minute")
async def connect_gmail(request: Request, response: Response, user: CurrentUser) -> ConnectOut:
    """Returns Google's consent URL; the browser goes there, then back to /gmail/callback."""
    settings = get_settings()
    if not settings.google_login_enabled:
        raise GoogleNotConfigured("Add GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET to .env.")
    state = secrets.token_urlsafe(24)
    pkce = google_oauth.new_pkce()
    response.set_cookie(
        STATE_COOKIE,
        security.sign_state({"state": state, "verifier": pkce.verifier, "uid": str(user.id)}),
        max_age=600,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        path=STATE_PATH,
    )
    return ConnectOut(url=gmail.consent_url(state, pkce.challenge, login_hint=user.email))


@router.get("/gmail/callback", response_class=RedirectResponse, status_code=302)
async def gmail_callback(
    request: Request,
    db: DbSession,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
) -> RedirectResponse:
    settings = get_settings()

    def back(result: str) -> RedirectResponse:
        resp = RedirectResponse(f"{settings.app_base_url}/settings?gmail={result}", 302)
        resp.delete_cookie(STATE_COOKIE, path=STATE_PATH)
        return resp

    stored = security.read_state(request.cookies.get(STATE_COOKIE, ""))
    if error or not code or not state or stored is None:
        return back("cancelled" if error else "expired")
    if not secrets.compare_digest(str(stored.get("state", "")), state):
        return back("expired")
    try:
        tokens = await gmail.exchange(code, str(stored["verifier"]))
        await integration_service.save_gmail(db, uuid.UUID(str(stored["uid"])), tokens)
    except gmail.GmailAuthError:
        return back("missing_permission")
    except (google_oauth.GoogleOAuthError, KeyError, ValueError) as exc:
        log.warning("gmail_connect_failed", error_type=type(exc).__name__)
        await db.rollback()
        return back("failed")
    return back("connected")


@router.delete("/{provider}", status_code=status.HTTP_204_NO_CONTENT)
async def disconnect(provider: IntegrationProvider, user: CurrentUser, db: DbSession) -> None:
    await integration_service.disconnect(db, user, provider)
