"""Connected Google services (Gmail now, Sheets in Phase 7). Tokens are stored encrypted."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.logging import get_logger
from app.integrations import gmail, google_oauth
from app.models import Integration, User
from app.models.enums import IntegrationProvider, IntegrationStatus
from app.schemas.integration import IntegrationOut, IntegrationsOut

log = get_logger(__name__)
REFRESH_EARLY = timedelta(minutes=2)


def send_backend() -> str:
    return get_settings().application_send_backend


async def get(
    db: AsyncSession, user_id: uuid.UUID, provider: IntegrationProvider
) -> Integration | None:
    row: Integration | None = await db.scalar(
        select(Integration).where(Integration.user_id == user_id, Integration.provider == provider)
    )
    return row


def to_out(provider: IntegrationProvider, row: Integration | None) -> IntegrationOut:
    if row is None:
        return IntegrationOut(
            provider=provider, status=IntegrationStatus.DISCONNECTED, google_email=None
        )
    return IntegrationOut(
        provider=provider,
        status=row.status,
        google_email=row.google_email,
        connected_at=row.created_at if row.status == IntegrationStatus.CONNECTED else None,
        last_error=row.last_error,
    )


async def overview(db: AsyncSession, user: User) -> IntegrationsOut:
    settings = get_settings()
    return IntegrationsOut(
        gmail=to_out(IntegrationProvider.GMAIL, await get(db, user.id, IntegrationProvider.GMAIL)),
        google_configured=settings.google_login_enabled,
        send_backend=settings.application_send_backend,
    )


async def save_gmail(db: AsyncSession, user_id: uuid.UUID, tokens: gmail.Tokens) -> Integration:
    info = await google_oauth.fetch_userinfo(tokens.access_token)
    row = await get(db, user_id, IntegrationProvider.GMAIL)
    if row is None:
        row = Integration(user_id=user_id, provider=IntegrationProvider.GMAIL)
        db.add(row)
    row.status = IntegrationStatus.CONNECTED
    row.google_email = info.email
    row.scopes = tokens.scopes
    row.access_token = tokens.access_token
    row.refresh_token = tokens.refresh_token or row.refresh_token
    row.token_expires_at = tokens.expires_at
    row.last_error = None
    await db.commit()
    log.info("integration_connected", provider="gmail")
    return row


async def disconnect(db: AsyncSession, user: User, provider: IntegrationProvider) -> None:
    row = await get(db, user.id, provider)
    if row is None:
        return
    token = row.refresh_token or row.access_token
    if token:
        await gmail.revoke(token)
    row.status = IntegrationStatus.DISCONNECTED
    row.access_token = None
    row.refresh_token = None
    row.token_expires_at = None
    await db.commit()


# --- worker side ---------------------------------------------------------------------------


def gmail_for(session: Session, user_id: uuid.UUID) -> Integration | None:
    row: Integration | None = session.scalar(
        select(Integration).where(
            Integration.user_id == user_id, Integration.provider == IntegrationProvider.GMAIL
        )
    )
    return row


def access_token(session: Session, row: Integration) -> str:
    """A valid access token, refreshed when it's about to expire (raises GmailAuthError)."""
    expires = row.token_expires_at
    if row.access_token and expires and expires - REFRESH_EARLY > datetime.now(UTC):
        return row.access_token
    if not row.refresh_token:
        raise gmail.GmailAuthError("Gmail isn't connected.")
    tokens = gmail.refresh(row.refresh_token)
    row.access_token = tokens.access_token
    row.refresh_token = tokens.refresh_token or row.refresh_token
    row.token_expires_at = tokens.expires_at
    session.flush()
    return tokens.access_token


def mark_needs_reauth(session: Session, row: Integration, reason: str) -> None:
    row.status = IntegrationStatus.NEEDS_REAUTH
    row.last_error = reason
    row.access_token = None
    session.flush()
