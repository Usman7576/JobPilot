"""API-side applications: prepare (queue the writer), read, edit, versions, flags, mark
applied. Writing happens in the worker (application_writer); this module never calls AI."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError, Conflict, NotFound, ServiceUnavailable
from app.core.logging import get_logger
from app.domain import fact_sheet as facts_mod
from app.domain import guardrails
from app.domain.guardrails import Report
from app.models import Application, ApplicationDraft, ApplicationEvent, Job, Resume, User, UserJob
from app.models.enums import (
    ApplicationChannel,
    ApplicationStatus,
    ContactSource,
    DraftKind,
    EventActor,
    ResumeStatus,
    Tone,
)
from app.schemas.application import (
    ApplicationListItem,
    ApplicationOut,
    ApplicationPatch,
    DraftOut,
    EventOut,
    FlagOut,
    PrepareIn,
    RegenerateIn,
)
from app.schemas.profile import ResumeProfile
from app.services.application_events import record_event

log = get_logger(__name__)
DONE = (
    ApplicationStatus.APPLIED,
    ApplicationStatus.REPLIED,
    ApplicationStatus.INTERVIEW,
    ApplicationStatus.OFFER,
    ApplicationStatus.REJECTED,
)
STUCK_AFTER = timedelta(minutes=10)  # a DRAFTING row older than this lost its worker


class NoResume(AppError):
    status_code, code, title = 422, "no_active_resume", "Upload a resume first"


class AlreadyApplied(AppError):
    status_code, code, title = 409, "already_applied", "Already applied"


class FlagsNotAcknowledged(AppError):
    status_code, code, title = 409, "flags_not_acknowledged", "Check the flagged claims first"


# --- reading -------------------------------------------------------------------------------


def _draft_out(d: ApplicationDraft) -> DraftOut:
    report = Report.from_json(d.guardrail_report)
    content: dict[str, Any] = dict(d.content or {})
    body = content.get("body")
    return DraftOut(
        id=d.id,
        kind=d.kind,
        tone=d.tone,
        content=content,
        flags=[FlagOut(**f.__dict__) for f in report.flags],
        blocked=report.blocked,
        verified=report.verified,
        word_count=guardrails.word_count(body) if isinstance(body, str) else None,
        model=d.model,
        edited_by_user=d.edited_by_user,
        created_at=d.created_at,
    )


async def _drafts(db: AsyncSession, application_id: uuid.UUID) -> list[ApplicationDraft]:
    rows = await db.scalars(
        select(ApplicationDraft)
        .where(ApplicationDraft.application_id == application_id)
        .order_by(ApplicationDraft.created_at.desc())
    )
    return list(rows)


def _is_generating(app: Application) -> bool:
    return (
        app.status == ApplicationStatus.DRAFTING
        and app.updated_at > datetime.now(UTC) - STUCK_AFTER
    )


async def to_out(db: AsyncSession, app: Application) -> ApplicationOut:
    job = await db.get(Job, app.job_id)
    resume = await db.get(Resume, app.resume_id) if app.resume_id else None
    drafts = await _drafts(db, app.id)
    versions: dict[str, list[DraftOut]] = {k.value: [] for k in DraftKind}
    for d in drafts:
        versions[d.kind.value].append(_draft_out(d))
    latest = {k: (v[0] if v else None) for k, v in versions.items()}
    events = await db.scalars(
        select(ApplicationEvent)
        .where(ApplicationEvent.application_id == app.id)
        .order_by(ApplicationEvent.created_at.desc())
        .limit(30)
    )
    current = [d for d in latest.values() if d is not None]
    return ApplicationOut(
        id=app.id,
        job_id=app.job_id,
        job_title=job.title if job else "Job removed",
        company_name=job.company_name if job else "",
        apply_url=(job.apply_url or job.primary_url) if job else None,
        status=app.status,
        channel=app.channel,
        tone=app.tone,
        contact_email=app.contact_email,
        email_source=app.email_source,
        email_confidence=app.email_confidence,
        email=latest["email"],
        cover_letter=latest["cover_letter"],
        resume_tweaks=latest["resume_tweaks"],
        follow_up=latest["follow_up"],
        follow_up_count=app.follow_up_count,
        versions={k: v for k, v in versions.items() if k != DraftKind.FOLLOW_UP.value},
        flags_blocked=any(d.blocked for d in current),
        flags_acknowledged=app.guardrail_flags_acknowledged_at is not None,
        sent_at=app.sent_at,
        follow_up_at=app.follow_up_at,
        last_error=app.last_error,
        notes=app.notes,
        resume_id=app.resume_id,
        resume_file_name=resume.file_name if resume else None,
        is_generating=_is_generating(app),
        events=[
            EventOut(
                from_status=e.from_status,
                to_status=e.to_status,
                actor=e.actor,
                reason=e.reason,
                created_at=e.created_at,
            )
            for e in events
        ],
        created_at=app.created_at,
        updated_at=app.updated_at,
    )


async def get_owned(db: AsyncSession, user: User, application_id: uuid.UUID) -> Application:
    app = await db.scalar(
        select(Application).where(Application.id == application_id, Application.user_id == user.id)
    )
    if app is None:
        raise NotFound("Application not found")
    return app


async def for_job(db: AsyncSession, user: User, job_id: uuid.UUID) -> Application | None:
    row: Application | None = await db.scalar(
        select(Application).where(Application.user_id == user.id, Application.job_id == job_id)
    )
    return row


async def list_for_user(db: AsyncSession, user: User) -> list[ApplicationListItem]:
    rows = await db.execute(
        select(Application, Job)
        .join(Job, Job.id == Application.job_id)
        .where(Application.user_id == user.id)
        .order_by(Application.updated_at.desc())
        .limit(200)
    )
    return [
        ApplicationListItem(
            id=a.id,
            job_id=a.job_id,
            job_title=j.title,
            company_name=j.company_name,
            status=a.status,
            channel=a.channel,
            contact_email=a.contact_email,
            sent_at=a.sent_at,
            updated_at=a.updated_at,
        )
        for a, j in rows.all()
    ]


# --- creating and writing --------------------------------------------------------------------


async def _user_job(db: AsyncSession, user: User, job_id: uuid.UUID) -> Job:
    job = await db.scalar(
        select(Job)
        .join(UserJob, UserJob.job_id == Job.id)
        .where(Job.id == job_id, UserJob.user_id == user.id)
    )
    if job is None:
        raise NotFound("Job not found")
    return job


async def _active_resume(db: AsyncSession, user: User) -> Resume:
    resume = await db.scalar(
        select(Resume).where(
            Resume.user_id == user.id,
            Resume.is_active.is_(True),
            Resume.status == ResumeStatus.PARSED,
        )
    )
    if resume is None:
        raise NoResume("Upload and parse a resume before preparing an application.")
    return resume


async def _get_or_create(db: AsyncSession, user: User, job: Job) -> Application:
    app = await for_job(db, user, job.id)
    if app is None:
        app = Application(user_id=user.id, job_id=job.id, status=ApplicationStatus.SAVED)
        db.add(app)
        await db.flush()
        record_event(db, app, ApplicationStatus.SAVED, EventActor.USER, "Saved")
    return app


async def save_for_later(db: AsyncSession, user: User, job_id: uuid.UUID) -> ApplicationOut:
    job = await _user_job(db, user, job_id)
    app = await _get_or_create(db, user, job)
    await db.commit()
    await db.refresh(app)
    return await to_out(db, app)


def _enqueue_prepare(
    app_id: uuid.UUID, kinds: list[str], tone: Tone, instructions: str | None
) -> None:
    from app.tasks.application_tasks import prepare_application

    prepare_application.delay(str(app_id), kinds, tone.value, instructions)


async def _start_writing(
    db: AsyncSession,
    app: Application,
    kinds: list[str],
    tone: Tone,
    instructions: str | None,
) -> ApplicationOut:
    if app.status in DONE:
        raise AlreadyApplied("You've already applied to this job.")
    if _is_generating(app):
        raise Conflict("Drafts for this job are already being written.")
    previous = app.status
    app.status = ApplicationStatus.DRAFTING
    app.tone = tone
    app.last_error = None
    app.updated_at = datetime.now(UTC)
    record_event(db, app, ApplicationStatus.DRAFTING, EventActor.USER, from_status=previous)
    await db.commit()
    try:
        _enqueue_prepare(app.id, kinds, tone, instructions)
    except Exception as exc:
        log.error("enqueue_failed", task="prepare_application", error_type=type(exc).__name__)
        app.status = previous
        app.last_error = "Couldn't start writing. Try again in a moment."
        await db.commit()
        raise ServiceUnavailable("Couldn't start writing. Try again in a moment.") from exc
    await db.refresh(app)
    return await to_out(db, app)


async def prepare(
    db: AsyncSession, user: User, job_id: uuid.UUID, body: PrepareIn
) -> ApplicationOut:
    job = await _user_job(db, user, job_id)
    resume = await _active_resume(db, user)
    app = await _get_or_create(db, user, job)
    app.resume_id = resume.id
    return await _start_writing(
        db, app, list(dict.fromkeys(body.kinds)), body.tone, body.instructions
    )


async def regenerate(
    db: AsyncSession, user: User, application_id: uuid.UUID, body: RegenerateIn
) -> ApplicationOut:
    app = await get_owned(db, user, application_id)
    if app.resume_id is None:
        app.resume_id = (await _active_resume(db, user)).id
    return await _start_writing(db, app, [body.kind], body.tone, body.instructions)


async def reverify(db: AsyncSession, user: User, application_id: uuid.UUID) -> None:
    from app.tasks.application_tasks import verify_application

    app = await get_owned(db, user, application_id)
    if not app.resume_id:
        raise NoResume("This application has no resume attached.")
    try:
        verify_application.delay(str(app.id))
    except Exception as exc:
        raise ServiceUnavailable("Couldn't start the fact-check. Try again.") from exc


# --- editing ---------------------------------------------------------------------------------


async def _facts(db: AsyncSession, app: Application) -> tuple[facts_mod.FactSheet, str]:
    resume = await db.get(Resume, app.resume_id) if app.resume_id else None
    job = await db.get(Job, app.job_id)
    if resume is None or resume.profile is None or job is None:
        raise NoResume("The resume used for this application is gone.")
    years = float(resume.total_years_experience) if resume.total_years_experience else None
    facts = facts_mod.build(ResumeProfile.model_validate(resume.profile), years)
    job_text = f"{job.title}\n{(job.description_text or '')[:4000]}"
    return facts, job_text


async def _latest(db: AsyncSession, app_id: uuid.UUID, kind: DraftKind) -> ApplicationDraft | None:
    row: ApplicationDraft | None = await db.scalar(
        select(ApplicationDraft)
        .where(ApplicationDraft.application_id == app_id, ApplicationDraft.kind == kind)
        .order_by(ApplicationDraft.created_at.desc())
        .limit(1)
    )
    return row


async def _edit_body(
    db: AsyncSession, app: Application, kind: DraftKind, text: str, subject: str | None = None
) -> None:
    draft = await _latest(db, app.id, kind)
    if draft is None:
        raise Conflict("There's no draft to edit yet.")
    facts, job_text = await _facts(db, app)
    content = dict(draft.content or {})
    content["body"] = text.strip()
    if subject is not None:
        content["subject"] = subject
    report = guardrails.check_text(content["body"], facts, job_text)
    # Edited text needs a fresh AI fact-check (Re-check); the fast checks run right away.
    report.verified = False
    draft.content = content
    draft.guardrail_report = report.to_json()
    draft.edited_by_user = True
    if report.blocked:
        app.guardrail_flags_acknowledged_at = None


async def patch(
    db: AsyncSession, user: User, application_id: uuid.UUID, body: ApplicationPatch
) -> ApplicationOut:
    app = await get_owned(db, user, application_id)
    if app.status in DONE or _is_generating(app):
        raise Conflict("This application can't be edited right now.")
    if body.email_body is not None or body.subject is not None:
        draft = await _latest(db, app.id, DraftKind.EMAIL)
        text = (
            body.email_body
            if body.email_body is not None
            else str((draft.content or {}).get("body", "") if draft else "")
        )
        await _edit_body(db, app, DraftKind.EMAIL, text, body.subject)
    if body.cover_letter_body is not None:
        await _edit_body(db, app, DraftKind.COVER_LETTER, body.cover_letter_body)
    if body.clear_contact:
        app.contact_email, app.email_source, app.email_confidence = None, ContactSource.NONE, None
        app.channel = ApplicationChannel.SITE
    elif body.contact_email is not None:
        app.contact_email = str(body.contact_email).lower()
        app.email_source = ContactSource.MANUAL
        app.email_confidence = None
        app.channel = ApplicationChannel.EMAIL
    if body.notes is not None:
        app.notes = body.notes or None
    app.updated_at = datetime.now(UTC)
    await db.commit()
    await db.refresh(app)
    return await to_out(db, app)


async def use_version(
    db: AsyncSession, user: User, application_id: uuid.UUID, draft_id: uuid.UUID
) -> ApplicationOut:
    """Make an older draft the current one (copied, so history stays as it was)."""
    app = await get_owned(db, user, application_id)
    old = await db.scalar(
        select(ApplicationDraft).where(
            ApplicationDraft.id == draft_id, ApplicationDraft.application_id == app.id
        )
    )
    if old is None:
        raise NotFound("Draft not found")
    copy = ApplicationDraft(
        application_id=app.id,
        kind=old.kind,
        tone=old.tone,
        content=old.content,
        guardrail_report=old.guardrail_report,
        prompt_version=old.prompt_version,
        model=old.model,
        edited_by_user=old.edited_by_user,
    )
    db.add(copy)
    await db.flush()
    if old.kind == DraftKind.EMAIL:
        app.current_draft_id = copy.id
    if Report.from_json(old.guardrail_report).blocked:
        app.guardrail_flags_acknowledged_at = None
    app.updated_at = datetime.now(UTC)
    await db.commit()
    await db.refresh(app)
    return await to_out(db, app)


async def acknowledge_flags(
    db: AsyncSession, user: User, application_id: uuid.UUID
) -> ApplicationOut:
    app = await get_owned(db, user, application_id)
    app.guardrail_flags_acknowledged_at = datetime.now(UTC)
    record_event(
        db,
        app,
        app.status,
        EventActor.USER,
        "Confirmed flagged claims are accurate",
        from_status=app.status,
    )
    await db.commit()
    await db.refresh(app)
    return await to_out(db, app)


async def mark_applied(
    db: AsyncSession, user: User, application_id: uuid.UUID, channel: str
) -> ApplicationOut:
    """The user applied themselves (on the site, or by sending the email from their inbox)."""
    app = await get_owned(db, user, application_id)
    if app.status in DONE:
        raise AlreadyApplied("Already marked as applied.")
    out = await to_out(db, app)
    if out.flags_blocked and app.guardrail_flags_acknowledged_at is None:
        raise FlagsNotAcknowledged("Fix or confirm the flagged claims before marking as applied.")
    previous = app.status
    now = datetime.now(UTC)
    app.status = ApplicationStatus.APPLIED
    app.channel = ApplicationChannel.SITE if channel == "site" else ApplicationChannel.EMAIL
    app.sent_at = now
    app.follow_up_at = now + timedelta(days=user.follow_up_days)
    reason = "Applied on the company site" if channel == "site" else "Sent from your own inbox"
    record_event(db, app, ApplicationStatus.APPLIED, EventActor.USER, reason, from_status=previous)
    await db.commit()
    await db.refresh(app)
    return await to_out(db, app)


async def delete(db: AsyncSession, user: User, application_id: uuid.UUID) -> None:
    app = await get_owned(db, user, application_id)
    await db.delete(app)
    await db.commit()
