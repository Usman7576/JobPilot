"""Sign-up, login, email verification, password reset, refresh rotation, Google login."""

from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import security
from app.core.config import get_settings
from app.core.errors import EmailNotVerified, InvalidCredentials, InvalidToken, Unauthorized
from app.core.logging import get_logger
from app.integrations.google_oauth import GoogleUserInfo
from app.models import (
    AuditLog,
    EmailVerification,
    OAuthAccount,
    PasswordReset,
    RefreshToken,
    User,
)
from app.models.enums import OAuthProvider
from app.providers.mailer import Mailer, OutgoingMail

log = get_logger(__name__)

# Spent on unknown emails so login timing doesn't reveal whether an account exists.
_DUMMY_HASH = security.hash_password("timing-equalizer-password")


@dataclass(frozen=True)
class SessionTokens:
    access_token: str
    refresh_token: str
    csrf_token: str


@dataclass(frozen=True)
class ClientInfo:
    user_agent: str | None
    ip: str | None

    @property
    def ip_hash(self) -> str | None:
        if not self.ip:
            return None
        salted = f"{get_settings().secret_key}:{self.ip}".encode()
        return hashlib.sha256(salted).hexdigest()[:32]


def _now() -> datetime:
    return datetime.now(UTC)


async def _audit(
    db: AsyncSession, action: str, user_id: uuid.UUID | None, client: ClientInfo | None = None
) -> None:
    db.add(AuditLog(user_id=user_id, action=action, ip_hash=client.ip_hash if client else None))


async def get_user_by_email(db: AsyncSession, email: str) -> User | None:
    return await db.scalar(select(User).where(User.email == email))


# --- Sign-up and email verification ---------------------------------------------------


async def signup(
    db: AsyncSession, mailer: Mailer, *, email: str, password: str, full_name: str | None
) -> None:
    """Always succeeds from the caller's view, so it can't be used to probe for accounts."""
    settings = get_settings()
    existing = await get_user_by_email(db, email)
    if existing is not None:
        if existing.email_verified_at is None:
            await send_verification(db, mailer, existing)
        await db.commit()
        return

    user = User(
        email=email,
        password_hash=security.hash_password(password),
        full_name=full_name,
        daily_send_cap=settings.default_daily_send_cap,
        follow_up_days=settings.default_follow_up_days,
        monthly_ai_budget_usd=settings.default_monthly_ai_budget_usd,
    )
    db.add(user)
    await db.flush()
    await _audit(db, "signup", user.id)
    await send_verification(db, mailer, user)
    await db.commit()


async def send_verification(db: AsyncSession, mailer: Mailer, user: User) -> None:
    settings = get_settings()
    token = security.new_opaque_token()
    db.add(
        EmailVerification(
            user_id=user.id,
            token_hash=security.hash_token(token),
            expires_at=_now() + timedelta(hours=settings.verification_token_ttl_hours),
        )
    )
    link = f"{settings.app_base_url}/verify?token={token}"
    await mailer.send(
        OutgoingMail(
            to=user.email,
            subject=f"Verify your {settings.app_name} email",
            text=(
                f"Welcome to {settings.app_name}!\n\nConfirm your email address:\n{link}\n\n"
                f"This link expires in {settings.verification_token_ttl_hours} hours."
            ),
        )
    )


async def resend_verification(db: AsyncSession, mailer: Mailer, email: str) -> None:
    user = await get_user_by_email(db, email)
    if user is not None and user.email_verified_at is None:
        await send_verification(db, mailer, user)
        await db.commit()


async def verify_email(db: AsyncSession, token: str) -> User:
    row = await db.scalar(
        select(EmailVerification).where(EmailVerification.token_hash == security.hash_token(token))
    )
    if row is None or row.used_at is not None or row.expires_at < _now():
        raise InvalidToken()
    user = await db.get(User, row.user_id)
    if user is None:
        raise InvalidToken()
    row.used_at = _now()
    user.email_verified_at = user.email_verified_at or _now()
    await db.commit()
    return user


# --- Login, sessions, refresh rotation --------------------------------------------------


async def authenticate(db: AsyncSession, *, email: str, password: str) -> User:
    user = await get_user_by_email(db, email)
    if user is None or user.password_hash is None:
        security.verify_password(password, _DUMMY_HASH)
        raise InvalidCredentials()
    if not security.verify_password(password, user.password_hash):
        raise InvalidCredentials()
    if not user.is_active or user.deletion_requested_at is not None:
        raise InvalidCredentials()
    if get_settings().require_email_verification and user.email_verified_at is None:
        raise EmailNotVerified()
    if security.password_needs_rehash(user.password_hash):
        user.password_hash = security.hash_password(password)
    return user


async def _issue_refresh(
    db: AsyncSession, user_id: uuid.UUID, family_id: uuid.UUID, client: ClientInfo
) -> tuple[RefreshToken, str]:
    token = security.new_opaque_token()
    row = RefreshToken(
        user_id=user_id,
        token_hash=security.hash_token(token),
        family_id=family_id,
        expires_at=_now() + timedelta(days=get_settings().refresh_token_ttl_days),
        user_agent=(client.user_agent or "")[:300] or None,
        ip_hash=client.ip_hash,
    )
    db.add(row)
    await db.flush()
    return row, token


async def start_session(db: AsyncSession, user: User, client: ClientInfo) -> SessionTokens:
    family_id = uuid.uuid4()
    _, refresh = await _issue_refresh(db, user.id, family_id, client)
    user.last_login_at = _now()
    await _audit(db, "login", user.id, client)
    await db.commit()
    return SessionTokens(
        access_token=security.create_access_token(user.id, family_id),
        refresh_token=refresh,
        csrf_token=security.new_opaque_token(),
    )


async def _revoke_family(db: AsyncSession, family_id: uuid.UUID) -> None:
    await db.execute(
        update(RefreshToken)
        .where(RefreshToken.family_id == family_id, RefreshToken.revoked_at.is_(None))
        .values(revoked_at=_now())
    )


async def rotate_refresh(db: AsyncSession, token: str, client: ClientInfo) -> SessionTokens:
    row = await db.scalar(
        select(RefreshToken)
        .where(RefreshToken.token_hash == security.hash_token(token))
        .with_for_update()
    )
    if row is None:
        raise Unauthorized()
    if row.revoked_at is not None:
        # A rotated-out token was presented again: assume theft, kill the whole session.
        await _revoke_family(db, row.family_id)
        await _audit(db, "refresh_token_reuse", row.user_id, client)
        await db.commit()
        log.warning("refresh_token_reuse", user_id=str(row.user_id))
        raise Unauthorized()
    if row.expires_at < _now():
        raise Unauthorized()
    user = await db.get(User, row.user_id)
    if user is None or not user.is_active or user.deletion_requested_at is not None:
        raise Unauthorized()

    new_row, new_token = await _issue_refresh(db, user.id, row.family_id, client)
    row.revoked_at = _now()
    row.replaced_by_id = new_row.id
    await db.commit()
    return SessionTokens(
        access_token=security.create_access_token(user.id, row.family_id),
        refresh_token=new_token,
        csrf_token=security.new_opaque_token(),
    )


async def logout(db: AsyncSession, token: str | None) -> None:
    if not token:
        return
    row = await db.scalar(
        select(RefreshToken).where(RefreshToken.token_hash == security.hash_token(token))
    )
    if row is not None:
        await _revoke_family(db, row.family_id)
        await _audit(db, "logout", row.user_id)
        await db.commit()


# --- Password reset ------------------------------------------------------------------


async def forgot_password(db: AsyncSession, mailer: Mailer, email: str) -> None:
    settings = get_settings()
    user = await get_user_by_email(db, email)
    if user is None or not user.is_active:
        return
    token = security.new_opaque_token()
    db.add(
        PasswordReset(
            user_id=user.id,
            token_hash=security.hash_token(token),
            expires_at=_now() + timedelta(minutes=settings.password_reset_ttl_minutes),
        )
    )
    await db.commit()
    link = f"{settings.app_base_url}/reset-password?token={token}"
    await mailer.send(
        OutgoingMail(
            to=user.email,
            subject=f"Reset your {settings.app_name} password",
            text=(
                f"Someone asked to reset your password. If it was you, open:\n{link}\n\n"
                f"This link expires in {settings.password_reset_ttl_minutes} minutes. "
                "If it wasn't you, ignore this email."
            ),
        )
    )


async def reset_password(db: AsyncSession, *, token: str, password: str) -> None:
    row = await db.scalar(
        select(PasswordReset).where(PasswordReset.token_hash == security.hash_token(token))
    )
    if row is None or row.used_at is not None or row.expires_at < _now():
        raise InvalidToken()
    user = await db.get(User, row.user_id)
    if user is None:
        raise InvalidToken()
    row.used_at = _now()
    user.password_hash = security.hash_password(password)
    # Clicking the emailed link proves inbox ownership.
    user.email_verified_at = user.email_verified_at or _now()
    await db.execute(
        update(RefreshToken)
        .where(RefreshToken.user_id == user.id, RefreshToken.revoked_at.is_(None))
        .values(revoked_at=_now())
    )
    await _audit(db, "password_reset", user.id)
    await db.commit()


# --- Google login --------------------------------------------------------------------


async def login_with_google(db: AsyncSession, info: GoogleUserInfo) -> User:
    if not info.email_verified:
        raise InvalidCredentials("Your Google email address is not verified")

    account = await db.scalar(
        select(OAuthAccount).where(
            OAuthAccount.provider == OAuthProvider.GOOGLE,
            OAuthAccount.provider_subject == info.subject,
        )
    )
    if account is not None:
        user = await db.get(User, account.user_id)
        if user is None:
            raise InvalidCredentials()
    else:
        user = await get_user_by_email(db, info.email)
        if user is None:
            settings = get_settings()
            user = User(
                email=info.email,
                full_name=info.name,
                email_verified_at=_now(),
                daily_send_cap=settings.default_daily_send_cap,
                follow_up_days=settings.default_follow_up_days,
                monthly_ai_budget_usd=settings.default_monthly_ai_budget_usd,
            )
            db.add(user)
            await db.flush()
            await _audit(db, "signup_google", user.id)
        db.add(
            OAuthAccount(
                user_id=user.id,
                provider=OAuthProvider.GOOGLE,
                provider_subject=info.subject,
                email=info.email,
            )
        )
        # Google verified this address, so a pending email verification is satisfied.
        user.email_verified_at = user.email_verified_at or _now()

    if not user.is_active or user.deletion_requested_at is not None:
        raise InvalidCredentials()
    await db.flush()
    return user
