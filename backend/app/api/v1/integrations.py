from __future__ import annotations

import secrets
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from fastapi import APIRouter, Request, Response, status
from fastapi.responses import RedirectResponse

from app.core import security
from app.core.config import get_settings
from app.core.deps import CurrentUser, DbSession
from app.core.errors import AppError, Conflict
from app.core.logging import get_logger
from app.core.ratelimit import limiter
from app.integrations import gmail, google_oauth, google_sheets
from app.models.enums import IntegrationProvider, IntegrationStatus
from app.schemas.integration import ConnectOut, IntegrationsOut
from app.services import integration_service, sheets_service

router = APIRouter(prefix="/integrations", tags=["integrations"])
log = get_logger(__name__)
STATE_COOKIE = "g_connect_state"
STATE_PATH = "/api/v1/integrations"


class GoogleNotConfigured(AppError):
    status_code, code, title = 409, "google_not_configured", "Google isn't set up"


@dataclass(frozen=True)
class _Flow:
    consent_url: Callable[[str, str, str | None], str]
    exchange: Callable[[str, str], Awaitable[gmail.Tokens]]
    missing_permission: tuple[type[Exception], ...]


# Each Google service is connected separately, with only the access it needs.
FLOWS: dict[IntegrationProvider, _Flow] = {
    IntegrationProvider.GMAIL: _Flow(gmail.consent_url, gmail.exchange, (gmail.GmailAuthError,)),
    IntegrationProvider.SHEETS: _Flow(
        google_sheets.consent_url, google_sheets.exchange, (google_sheets.SheetsAuthError,)
    ),
}


@router.get("")
async def list_integrations(user: CurrentUser, db: DbSession) -> IntegrationsOut:
    return await integration_service.overview(db, user)


@router.get("/{provider}/connect")
@limiter.limit("10/minute")
async def connect(
    request: Request, response: Response, provider: IntegrationProvider, user: CurrentUser
) -> ConnectOut:
    """Returns Google's consent URL; the browser goes there, then back to the callback."""
    settings = get_settings()
    if not settings.google_login_enabled:
        raise GoogleNotConfigured("Add GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET to .env.")
    state = secrets.token_urlsafe(24)
    pkce = google_oauth.new_pkce()
    response.set_cookie(
        STATE_COOKIE,
        security.sign_state(
            {"state": state, "verifier": pkce.verifier, "uid": str(user.id), "p": provider.value}
        ),
        max_age=600,
        httponly=True,
        secure=settings.cookie_secure,
        samesite="lax",
        path=STATE_PATH,
    )
    url = FLOWS[provider].consent_url(state, pkce.challenge, user.email)
    return ConnectOut(url=url)


@router.get("/{provider}/callback", response_class=RedirectResponse, status_code=302)
async def callback(
    request: Request,
    provider: IntegrationProvider,
    db: DbSession,
    code: str | None = None,
    state: str | None = None,
    error: str | None = None,
) -> RedirectResponse:
    settings = get_settings()

    def back(result: str) -> RedirectResponse:
        resp = RedirectResponse(f"{settings.app_base_url}/settings?{provider.value}={result}", 302)
        resp.delete_cookie(STATE_COOKIE, path=STATE_PATH)
        return resp

    stored = security.read_state(request.cookies.get(STATE_COOKIE, ""))
    if error or not code or not state or stored is None:
        return back("cancelled" if error else "expired")
    if stored.get("p") != provider.value or not secrets.compare_digest(
        str(stored.get("state", "")), state
    ):
        return back("expired")
    flow = FLOWS[provider]
    try:
        tokens = await flow.exchange(code, str(stored["verifier"]))
        user_id = uuid.UUID(str(stored["uid"]))
        await integration_service.save(db, user_id, provider, tokens)
    except flow.missing_permission:
        return back("missing_permission")
    except (google_oauth.GoogleOAuthError, KeyError, ValueError) as exc:
        log.warning("connect_failed", provider=provider.value, error_type=type(exc).__name__)
        await db.rollback()
        return back("failed")
    if provider == IntegrationProvider.SHEETS:
        sheets_service.request_sync(user_id, now=True)  # creates the tracker sheet
    return back("connected")


@router.post("/sheets/sync", status_code=status.HTTP_202_ACCEPTED)
@limiter.limit("10/minute")
async def sync_sheets(request: Request, user: CurrentUser, db: DbSession) -> None:
    """Rewrite the tracker sheet now (it also updates itself a few minutes after changes)."""
    row = await integration_service.get(db, user.id, IntegrationProvider.SHEETS)
    if row is None or row.status != IntegrationStatus.CONNECTED:
        raise Conflict("Connect Google Sheets first.")
    sheets_service.request_sync(user.id, now=True)


@router.delete("/{provider}", status_code=status.HTTP_204_NO_CONTENT)
async def disconnect(provider: IntegrationProvider, user: CurrentUser, db: DbSession) -> None:
    await integration_service.disconnect(db, user, provider)
