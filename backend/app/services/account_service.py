"""Your data: export everything as a zip, or delete the account and everything in it.

Deletion happens in two steps. The request (API) signs you out everywhere, revokes Google
access and locks the account at once; a worker then deletes the stored files and the user
row, and every table cascades from it. Shared job postings stay (they aren't personal);
the Google Sheet you own stays in your Drive.
"""

from __future__ import annotations

import contextlib
import io
import json
import uuid
import zipfile
from datetime import UTC, date, datetime
from decimal import Decimal
from enum import Enum
from typing import Any

from sqlalchemy import inspect, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from app.core import crypto
from app.core.errors import AppError
from app.core.logging import get_logger
from app.models import (
    Application,
    ApplicationDraft,
    ApplicationEvent,
    Integration,
    Job,
    JobMatch,
    Notification,
    Preference,
    RefreshToken,
    Resume,
    SearchRun,
    UsageEvent,
    User,
    UserJob,
)
from app.models.enums import IntegrationProvider
from app.providers.storage import get_storage
from app.services import integration_service

log = get_logger(__name__)
CONFIRM_WORD = "DELETE"
# Secrets and bulky internals never leave the database, even in your own export.
_SKIP = {
    "password_hash", "access_token", "refresh_token", "token_hash", "embedding",
    "file_key", "file_sha256", "ip_hash",
}  # fmt: skip


class ConfirmationMismatch(AppError):
    status_code, code, title = 422, "confirmation_mismatch", "Type DELETE to confirm"


def _plain(value: Any) -> Any:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, bytes):
        return None
    return value


def _row(obj: Any) -> dict[str, Any]:
    mapper = inspect(obj).mapper
    return {
        attr.key: _plain(getattr(obj, attr.key))
        for attr in mapper.column_attrs
        if attr.key not in _SKIP
    }


async def _all(db: AsyncSession, stmt: Any) -> list[dict[str, Any]]:
    return [_row(r) for r in (await db.scalars(stmt)).all()]


async def export_zip(db: AsyncSession, user: User) -> bytes:
    """Everything stored about you, as JSON files plus your original resume files."""
    resumes = (await db.scalars(select(Resume).where(Resume.user_id == user.id))).all()
    app_ids = select(Application.id).where(Application.user_id == user.id)
    jobs = await db.execute(
        select(Job, UserJob)
        .join(UserJob, UserJob.job_id == Job.id)
        .where(UserJob.user_id == user.id)
    )
    files: dict[str, Any] = {
        "account.json": _row(user),
        "preferences.json": await _all(db, select(Preference).where(Preference.user_id == user.id)),
        "resumes.json": [_row(r) for r in resumes],
        "jobs.json": [{**_row(job), "your_status": _row(uj)} for job, uj in jobs.all()],
        "matches.json": await _all(db, select(JobMatch).where(JobMatch.user_id == user.id)),
        "applications.json": await _all(
            db, select(Application).where(Application.user_id == user.id)
        ),
        "drafts.json": await _all(
            db, select(ApplicationDraft).where(ApplicationDraft.application_id.in_(app_ids))
        ),
        "application_events.json": await _all(
            db, select(ApplicationEvent).where(ApplicationEvent.application_id.in_(app_ids))
        ),
        "searches.json": await _all(db, select(SearchRun).where(SearchRun.user_id == user.id)),
        "notifications.json": await _all(
            db, select(Notification).where(Notification.user_id == user.id)
        ),
        "ai_usage.json": await _all(db, select(UsageEvent).where(UsageEvent.user_id == user.id)),
        "connected_accounts.json": await _all(
            db, select(Integration).where(Integration.user_id == user.id)
        ),
    }
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(
            "README.txt",
            "Your JobPilot AI data, exported "
            f"{datetime.now(UTC):%Y-%m-%d %H:%M} UTC.\n"
            "Each .json file holds one kind of record. Passwords and access tokens are never "
            "exported. Your original resume files are in resumes/.\n",
        )
        for name, data in files.items():
            zf.writestr(name, json.dumps(data, indent=2, ensure_ascii=False))
        storage = get_storage()
        for r in resumes:
            try:
                blob = storage.get(r.file_key)
            except FileNotFoundError:
                continue
            zf.writestr(f"resumes/v{r.version}_{r.file_name}", crypto.decrypt_file(blob))
    return buffer.getvalue()


async def request_deletion(db: AsyncSession, user: User, confirm: str) -> None:
    if confirm.strip() != CONFIRM_WORD:
        raise ConfirmationMismatch(f"Type {CONFIRM_WORD} (in capitals) to delete your account.")
    for provider in IntegrationProvider:  # revokes the Google tokens too
        await integration_service.disconnect(db, user, provider)
    await db.execute(
        update(RefreshToken)
        .where(RefreshToken.user_id == user.id, RefreshToken.revoked_at.is_(None))
        .values(revoked_at=datetime.now(UTC))
    )
    user.deletion_requested_at = datetime.now(UTC)
    user.is_active = False
    await db.commit()
    log.info("account_deletion_requested", user_id=str(user.id))

    from app.tasks.account_tasks import purge_account

    try:
        purge_account.delay(str(user.id))
    except Exception as exc:  # the hourly sweep purges it anyway
        log.error("enqueue_failed", task="purge_account", error_type=type(exc).__name__)


# --- worker side ---------------------------------------------------------------------------


def purge(session: Session, user_id: uuid.UUID) -> bool:
    """Delete the user's files, then the user (every table cascades). Idempotent."""
    user = session.get(User, user_id)
    if user is None:
        return False
    if user.deletion_requested_at is None:
        return False  # never purge an account that didn't ask for it
    storage = get_storage()
    for key in session.scalars(select(Resume.file_key).where(Resume.user_id == user_id)):
        with contextlib.suppress(FileNotFoundError):
            storage.delete(key)
    session.delete(user)
    session.commit()
    log.info("account_purged", user_id=str(user_id))
    return True


def pending_deletions(session: Session) -> list[uuid.UUID]:
    return list(session.scalars(select(User.id).where(User.deletion_requested_at.is_not(None))))
