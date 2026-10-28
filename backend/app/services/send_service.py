"""Sending an application email from the user's own Gmail.

A person is always in the loop: the only way in is POST /applications/{id}/send, which needs
the preview dialog's confirmation, an Idempotency-Key and resolved fact-check flags. That
endpoint sets QUEUED with a random 30-120 s delay (sends from one user >= 30 s apart), and
the user can cancel until it goes. The worker task sends only an application that is still
QUEUED, under a row lock, so a cancel and a send can never both win.

The daily cap counts today's sends (user's timezone) plus the ones waiting in the queue, and
is checked again right before sending.
"""

from __future__ import annotations

import random
import smtplib
import uuid
from datetime import UTC, date, datetime, timedelta
from email.message import EmailMessage
from email.utils import formataddr, make_msgid
from urllib.parse import unquote, urlparse
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from app.core import crypto
from app.core.config import get_settings
from app.core.errors import AppError, Conflict
from app.core.logging import get_logger
from app.integrations import gmail
from app.models import Application, EmailSendLog, Notification, Resume, User
from app.models.enums import (
    ApplicationChannel,
    ApplicationStatus,
    EventActor,
    IntegrationProvider,
    IntegrationStatus,
    NotificationKind,
    SendStatus,
)
from app.providers.storage import get_storage
from app.schemas.application import ApplicationOut, SendQuotaOut
from app.services import application_service, integration_service, sheets_service
from app.services.application_events import record_event

log = get_logger(__name__)
S = ApplicationStatus
MAX_ATTEMPTS = 3  # Gmail busy (429/5xx): retried a minute apart, then given up
RETRY_SECONDS = 60
SENDABLE = (S.SAVED, S.READY)


class SendNotAllowed(AppError):
    status_code, code, title = 422, "send_not_allowed", "Can't send this yet"


class GmailNotConnected(AppError):
    status_code, code, title = 409, "gmail_not_connected", "Connect Gmail first"


class DailyCapReached(AppError):
    status_code, code, title = 429, "daily_send_cap", "Daily send limit reached"


# --- shared rules ------------------------------------------------------------------------------


def _zone(user: User) -> ZoneInfo:
    try:
        return ZoneInfo(user.timezone or "UTC")
    except (ZoneInfoNotFoundError, ValueError):
        return ZoneInfo("UTC")


def local_day(user: User, now: datetime | None = None) -> date:
    return (now or datetime.now(UTC)).astimezone(_zone(user)).date()


def _sent_today_stmt(user: User, now: datetime | None = None):  # type: ignore[no-untyped-def]
    return select(func.count(EmailSendLog.id)).where(
        EmailSendLog.user_id == user.id,
        EmailSendLog.status == SendStatus.SENT,
        EmailSendLog.sent_on == local_day(user, now),
    )


def _queued_stmt(user: User):  # type: ignore[no-untyped-def]
    return select(func.count(Application.id)).where(
        Application.user_id == user.id, Application.status == S.QUEUED
    )


def email_parts(app: ApplicationOut) -> tuple[str, str]:
    """(subject, text) exactly as the preview shows them: body, then signature."""
    content = dict(app.email.content if app.email else {})
    subject = str(content.get("subject") or "").strip()
    text = "\n\n".join(
        str(content[k]).strip() for k in ("body", "signature") if str(content.get(k) or "").strip()
    )
    return subject, text


# --- API side ----------------------------------------------------------------------------------


async def quota(db: AsyncSession, user: User) -> SendQuotaOut:
    sent = int(await db.scalar(_sent_today_stmt(user)) or 0)
    queued = int(await db.scalar(_queued_stmt(user)) or 0)
    return SendQuotaOut(
        cap=user.daily_send_cap,
        sent_today=sent,
        queued=queued,
        remaining=max(0, user.daily_send_cap - sent - queued),
    )


async def _next_slot(db: AsyncSession, user: User, now: datetime) -> datetime:
    settings = get_settings()
    delay = random.uniform(  # noqa: S311 - a human-like delay, not a secret
        settings.send_delay_min_seconds, settings.send_delay_max_seconds
    )
    slot = now + timedelta(seconds=delay)
    latest = await db.scalar(
        select(func.max(func.greatest(Application.scheduled_send_at, Application.sent_at))).where(
            Application.user_id == user.id,
            (Application.status == S.QUEUED) | (Application.channel == ApplicationChannel.EMAIL),
        )
    )
    if latest is not None:
        slot = max(slot, latest + timedelta(seconds=settings.send_spacing_seconds))
    return slot


def _enqueue(application_id: uuid.UUID, task_id: str, eta: datetime) -> None:
    from app.tasks.email_tasks import send_application_email

    send_application_email.apply_async((str(application_id),), task_id=task_id, eta=eta)


async def send(
    db: AsyncSession,
    user: User,
    application_id: uuid.UUID,
    *,
    idempotency_key: str,
    preview_confirmed: bool,
) -> ApplicationOut:
    key = f"{user.id}:{idempotency_key.strip()[:200]}"
    # Lock the user row: two sends at once can't both squeeze under the cap.
    await db.execute(select(User.id).where(User.id == user.id).with_for_update())
    app = await application_service.get_owned(db, user, application_id)
    if app.idempotency_key == key and app.status in (S.QUEUED, *application_service.DONE):
        return await application_service.to_out(db, app)  # a retried click: same answer
    if not preview_confirmed:
        raise SendNotAllowed("Review the final email in the preview and confirm it.")
    if app.status == S.QUEUED:
        raise Conflict("This email is already scheduled to send.")
    if app.status in application_service.DONE:
        raise application_service.AlreadyApplied("You've already applied to this job.")
    if app.status not in SENDABLE or application_service._is_generating(app):
        raise Conflict("Drafts are still being written.")

    out = await application_service.to_out(db, app)
    subject, text = email_parts(out)
    if not out.email or not subject or not text:
        raise SendNotAllowed("Write the email first (it needs a subject and a body).")
    if not app.contact_email:
        raise SendNotAllowed("Add the address to send to first.")
    if out.flags_blocked and app.guardrail_flags_acknowledged_at is None:
        raise application_service.FlagsNotAcknowledged(
            "Fix or confirm the flagged claims before sending."
        )
    if integration_service.send_backend() == "gmail":
        row = await integration_service.get(db, user.id, IntegrationProvider.GMAIL)
        if row is None or row.status != IntegrationStatus.CONNECTED:
            raise GmailNotConnected("Connect Gmail in Settings to send from the app.")
    q = await quota(db, user)
    if q.remaining <= 0:
        raise DailyCapReached(
            f"You've reached today's limit of {q.cap} emails. Change it in Settings, "
            "or send this one tomorrow."
        )

    now = datetime.now(UTC)
    previous = app.status
    task_id = str(uuid.uuid4())
    app.status = S.QUEUED
    app.channel = ApplicationChannel.EMAIL
    app.subject, app.body = subject, text  # the snapshot that will go out
    app.queued_at = now
    app.scheduled_send_at = await _next_slot(db, user, now)
    app.send_task_id = task_id
    app.idempotency_key = key
    app.last_error = None
    record_event(
        db, app, S.QUEUED, EventActor.USER, f"Scheduled to send to {app.contact_email}",
        from_status=previous,
    )  # fmt: skip
    await db.commit()
    try:
        _enqueue(app.id, task_id, app.scheduled_send_at)
    except Exception as exc:
        log.error("enqueue_failed", task="send_application_email", error_type=type(exc).__name__)
        await db.refresh(app)
        if app.status == S.QUEUED:
            _unqueue(app)
            app.status = previous
            app.last_error = "Couldn't schedule the email. Try again in a moment."
            await db.commit()
        raise AppError("Couldn't schedule the email. Try again in a moment.") from exc
    await db.refresh(app)
    return await application_service.to_out(db, app)


def _unqueue(app: Application) -> None:
    app.queued_at = None
    app.scheduled_send_at = None
    app.send_task_id = None
    app.idempotency_key = None


def revoke(task_id: str | None) -> None:
    """Best effort: the task re-checks the status anyway, so a missed revoke is harmless."""
    if not task_id:
        return
    try:
        from app.tasks.celery_app import celery_app

        celery_app.control.revoke(task_id)
    except Exception as exc:
        log.warning("revoke_failed", error_type=type(exc).__name__)


async def cancel(db: AsyncSession, user: User, application_id: uuid.UUID) -> ApplicationOut:
    app = await db.scalar(
        select(Application)
        .where(Application.id == application_id, Application.user_id == user.id)
        .with_for_update()  # waits if the worker is sending right now
    )
    if app is None:
        await application_service.get_owned(db, user, application_id)  # raises NotFound
        raise AssertionError  # pragma: no cover
    if app.status != S.QUEUED:
        if app.status in application_service.DONE:
            raise Conflict("Too late: this email has already been sent.")
        raise Conflict("This email isn't scheduled.")
    task_id = app.send_task_id
    _unqueue(app)
    app.status = S.READY
    record_event(db, app, S.READY, EventActor.USER, "Send cancelled", from_status=S.QUEUED)
    await db.commit()
    revoke(task_id)
    await db.refresh(app)
    return await application_service.to_out(db, app)


# --- worker side -------------------------------------------------------------------------------


def _attachment_name(user: User, resume: Resume) -> str:
    profile = resume.profile or {}
    name = str((profile.get("contact") or {}).get("name") or user.full_name or "").strip()
    ext = resume.file_name.rsplit(".", 1)[-1].lower() if "." in resume.file_name else "pdf"
    stem = "_".join(p for p in name.replace(".", " ").split() if p.isalnum()) or "My"
    return f"{stem}_Resume.{ext}"


def build_message(session: Session, app: Application, user: User, sender: str) -> EmailMessage:
    """Plain text (as previewed) plus the resume used for this application, if it's there."""
    msg = EmailMessage()
    msg["From"] = formataddr((user.full_name or "", sender)) if user.full_name else sender
    msg["To"] = app.contact_email or ""
    msg["Subject"] = app.subject or ""
    msg["Message-ID"] = make_msgid(domain=sender.rsplit("@", 1)[-1] if "@" in sender else None)
    msg.set_content(app.body or "")
    resume = session.get(Resume, app.resume_id) if app.resume_id else None
    if resume is not None:
        try:
            data = crypto.decrypt_file(get_storage().get(resume.file_key))
        except FileNotFoundError:
            log.warning("resume_file_missing")
        else:
            maintype, _, subtype = (resume.mime_type or "application/pdf").partition("/")
            msg.add_attachment(
                data,
                maintype=maintype,
                subtype=subtype or "octet-stream",
                filename=_attachment_name(user, resume),
            )
    return msg


def _send_smtp(msg: EmailMessage) -> gmail.Sent:
    """Local test mode (APPLICATION_SEND_BACKEND=smtp): delivers to SMTP_URL, i.e. Mailpit."""
    url = urlparse(get_settings().smtp_url)
    try:
        cls = smtplib.SMTP_SSL if url.scheme == "smtps" else smtplib.SMTP
        with cls(url.hostname or "localhost", url.port or 1025, timeout=20) as smtp:
            if url.scheme == "smtp+starttls":
                smtp.starttls()
            if url.username:
                smtp.login(unquote(url.username), unquote(url.password or ""))
            smtp.send_message(msg)
    except (smtplib.SMTPException, OSError) as exc:
        raise gmail.GmailSendError(
            "The test mail server didn't accept it.", retryable=True
        ) from exc
    return gmail.Sent(message_id=str(msg["Message-ID"]), thread_id=None)


def _fail(
    session: Session, app: Application, user: User, reason: str, *, log_failure: bool = True
) -> None:
    _unqueue(app)
    app.status = S.READY
    app.last_error = reason
    record_event(session, app, S.READY, EventActor.SYSTEM, f"Not sent: {reason}",
                 from_status=S.QUEUED)  # fmt: skip
    if log_failure:
        session.add(
            EmailSendLog(
                user_id=user.id, application_id=app.id, status=SendStatus.FAILED,
                sent_on=local_day(user),
            )
        )  # fmt: skip
    session.add(
        Notification(
            user_id=user.id,
            kind=NotificationKind.SEND_FAILED,
            title="Email not sent",
            body=reason,
            link=f"/applications/{app.id}",
        )
    )


def deliver(session: Session, application_id: uuid.UUID, attempt: int = 1) -> str:
    """Send one queued application. Returns sent / skipped / failed / retry."""
    app = session.scalar(
        select(Application).where(Application.id == application_id).with_for_update()
    )
    if app is None or app.status != S.QUEUED:
        return "skipped"  # cancelled, deleted or moved meanwhile
    user = session.get(User, app.user_id)
    assert user is not None
    if not app.contact_email or not app.body:
        _fail(session, app, user, "The email or its address was missing.", log_failure=False)
        session.commit()
        return "failed"
    sent_today = int(session.scalar(_sent_today_stmt(user)) or 0)
    if sent_today >= user.daily_send_cap:
        _fail(session, app, user, f"Today's limit of {user.daily_send_cap} emails was reached.",
              log_failure=False)  # fmt: skip
        session.commit()
        return "failed"

    row = None
    try:
        if integration_service.send_backend() == "smtp":
            sent = _send_smtp(build_message(session, app, user, "me@jobpilot.local"))
        else:
            row = integration_service.gmail_for(session, user.id)
            if row is None or row.status != IntegrationStatus.CONNECTED:
                raise gmail.GmailAuthError("Gmail isn't connected. Connect it in Settings.")
            token = integration_service.access_token(session, row)
            msg = build_message(session, app, user, row.google_email or user.email)
            sent = gmail.send_raw(token, msg.as_bytes())
    except gmail.GmailAuthError as exc:
        if row is not None:
            integration_service.mark_needs_reauth(session, row, str(exc))
        _fail(session, app, user, f"{exc} Then send it again.")
        session.commit()
        return "failed"
    except gmail.GmailSendError as exc:
        if exc.retryable and attempt < MAX_ATTEMPTS:
            app.scheduled_send_at = datetime.now(UTC) + timedelta(seconds=RETRY_SECONDS)
            session.commit()
            return "retry"
        _fail(session, app, user, str(exc))
        session.commit()
        return "failed"

    now = datetime.now(UTC)
    app.status = S.APPLIED
    app.sent_at = now
    app.follow_up_at = now + timedelta(days=user.follow_up_days)
    app.gmail_message_id = sent.message_id
    app.gmail_thread_id = sent.thread_id
    app.send_task_id = None
    app.last_error = None
    session.add(
        EmailSendLog(user_id=user.id, application_id=app.id, status=SendStatus.SENT,
                     sent_on=local_day(user, now))
    )  # fmt: skip
    record_event(session, app, S.APPLIED, EventActor.SYSTEM, f"Sent to {app.contact_email}",
                 from_status=S.QUEUED)  # fmt: skip
    session.commit()
    log.info("application_sent", attempt=attempt)
    sheets_service.request_sync(user.id)
    return "sent"
