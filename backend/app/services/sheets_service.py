"""Keep the user's "JobPilot AI Tracker" spreadsheet in step with the app (one-way mirror).

Changes queue one sync 5 minutes later (a Redis key dedupes them), so a burst of edits is
a single write; "Sync now" runs it at once. Each sync rewrites both tabs.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from functools import lru_cache
from typing import Any

from redis import Redis
from sqlalchemy import and_, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.logging import get_logger
from app.integrations import gmail, google_sheets
from app.models import Application, Integration, Job, JobMatch, JobSourceRecord, UserJob
from app.models.enums import IntegrationProvider, IntegrationStatus
from app.services import integration_service, matching

log = get_logger(__name__)
DEBOUNCE_SECONDS = 300
MAX_ROWS = 2000
JOB_HEADER = ["job_id", "title", "company", "location", "remote", "source", "score",
              "recommendation", "posted_at", "url", "discovered_at", "status"]  # fmt: skip
APP_HEADER = ["application_id", "job_title", "company", "channel", "contact_email", "status",
              "sent_at", "last_reply_at", "follow_up_at", "url"]  # fmt: skip


@lru_cache
def _redis() -> Redis:
    return Redis.from_url(get_settings().redis_url)


def request_sync(user_id: uuid.UUID, *, now: bool = False) -> None:
    """Queue a sync for this user (debounced unless `now`). Never raises."""
    from app.tasks.sheets_tasks import sync_sheet

    try:
        if now:
            sync_sheet.delay(str(user_id))
        elif _redis().set(f"sheets:pending:{user_id}", 1, nx=True, ex=DEBOUNCE_SECONDS):
            sync_sheet.apply_async((str(user_id),), countdown=DEBOUNCE_SECONDS)
    except Exception as exc:  # the sheet is a convenience; never break the main action
        log.warning("sheets_enqueue_failed", error_type=type(exc).__name__)


def _iso(value: datetime | None) -> str:
    return value.astimezone(UTC).strftime("%Y-%m-%d %H:%M") if value else ""


def job_rows(session: Session, user_id: uuid.UUID) -> list[list[Any]]:
    resume = matching.active_resume(session, user_id)
    match_on = (
        and_(
            JobMatch.job_id == Job.id,
            JobMatch.resume_id == resume.id,
            JobMatch.profile_version == resume.profile_version,
        )
        if resume
        else JobMatch.id.is_(None)
    )
    rows = session.execute(
        select(Job, UserJob, JobMatch, Application.status)
        .join(UserJob, and_(UserJob.job_id == Job.id, UserJob.user_id == user_id))
        .outerjoin(JobMatch, match_on)
        .outerjoin(Application, and_(Application.job_id == Job.id, Application.user_id == user_id))
        .where(UserJob.dismissed_at.is_(None))
        .order_by(UserJob.discovered_at.desc())
        .limit(MAX_ROWS)
    ).all()
    sources: dict[uuid.UUID, set[str]] = {}
    if rows:
        for job_id, source in session.execute(
            select(JobSourceRecord.job_id, JobSourceRecord.source).where(
                JobSourceRecord.job_id.in_([r[0].id for r in rows])
            )
        ):
            sources.setdefault(job_id, set()).add(source)
    out: list[list[Any]] = [JOB_HEADER]
    for job, user_job, match, status in rows:
        out.append(
            [
                str(job.id),
                job.title,
                job.company_name,
                job.location_raw or "",
                job.remote_type.value,
                ", ".join(sorted(sources.get(job.id, ()))),
                match.overall_score if match and match.overall_score is not None else "",
                match.recommendation.value if match and match.recommendation else "",
                _iso(job.posted_at),
                job.apply_url or job.primary_url,
                _iso(user_job.discovered_at),
                status.value if status else "",
            ]
        )
    return out


def application_rows(session: Session, user_id: uuid.UUID) -> list[list[Any]]:
    rows = session.execute(
        select(Application, Job)
        .join(Job, Job.id == Application.job_id)
        .where(Application.user_id == user_id)
        .order_by(Application.updated_at.desc())
        .limit(MAX_ROWS)
    ).all()
    out: list[list[Any]] = [APP_HEADER]
    for app, job in rows:
        out.append(
            [
                str(app.id),
                job.title,
                job.company_name,
                app.channel.value,
                app.contact_email or "",
                app.status.value,
                _iso(app.sent_at),
                _iso(app.last_reply_at),
                _iso(app.follow_up_at),
                job.apply_url or job.primary_url,
            ]
        )
    return out


def _integration(session: Session, user_id: uuid.UUID) -> Integration | None:
    row: Integration | None = session.scalar(
        select(Integration).where(
            Integration.user_id == user_id, Integration.provider == IntegrationProvider.SHEETS
        )
    )
    return row


def sync(session: Session, user_id: uuid.UUID) -> bool:
    """Write both tabs, creating the spreadsheet first if needed. False if not connected."""
    _redis().delete(f"sheets:pending:{user_id}")
    row = _integration(session, user_id)
    if row is None or row.status != IntegrationStatus.CONNECTED:
        return False
    try:
        token = integration_service.access_token(session, row)
        config = dict(row.config or {})
        if not config.get("spreadsheet_id"):
            sheet = google_sheets.create(token)
            config = {"spreadsheet_id": sheet.id, "spreadsheet_url": sheet.url}
            row.config = config
            session.commit()
        google_sheets.write(
            token,
            config["spreadsheet_id"],
            {
                "Jobs": job_rows(session, user_id),
                "Applications": application_rows(session, user_id),
            },
        )
    except (google_sheets.SheetsAuthError, gmail.GmailAuthError) as exc:
        integration_service.mark_needs_reauth(session, row, str(exc))
        session.commit()
        return False
    except google_sheets.SheetsError as exc:
        if exc.gone:  # deleted by the user: a fresh sheet on the next sync
            row.config = {}
        row.last_error = str(exc)
        session.commit()
        log.warning("sheets_sync_failed", gone=exc.gone)
        return False
    except gmail.GmailSendError as exc:  # token refresh couldn't reach Google
        row.last_error = str(exc)
        session.commit()
        return False
    row.last_sync_at = datetime.now(UTC)
    row.last_error = None
    session.commit()
    return True
