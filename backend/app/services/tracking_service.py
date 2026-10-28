"""After applying: the board (moves between columns), follow-ups, notifications, dashboard."""

from __future__ import annotations

import uuid
from collections import Counter
from datetime import UTC, date, datetime, timedelta
from typing import Any

from sqlalchemy import Date, and_, cast, exists, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError, Conflict, NotFound, ServiceUnavailable
from app.domain import board
from app.models import (
    Application,
    ApplicationDraft,
    ApplicationEvent,
    Job,
    JobMatch,
    Notification,
    User,
    UserJob,
)
from app.models.enums import (
    ApplicationChannel,
    ApplicationStatus,
    EventActor,
    MatchStage,
    NotificationKind,
    Tone,
)
from app.schemas.tracking import (
    BoardCard,
    DashboardOut,
    FunnelStep,
    MoveIn,
    NotificationOut,
    NotificationsOut,
    SkillGap,
    StatCards,
    WeekPoint,
)
from app.services import application_service, job_service
from app.services.application_events import record_event

S = ApplicationStatus
MAX_FOLLOW_UPS = 2
GOOD_MATCH = 65  # "apply" band and up: the matches whose missing skills matter


class NotAppliedYet(AppError):
    status_code, code, title = 409, "not_applied", "Apply first"


# --- board ---------------------------------------------------------------------------------


def _card(app: Application, job: Job, score: int | None, now: datetime) -> BoardCard:
    return BoardCard(
        id=app.id,
        job_id=app.job_id,
        job_title=job.title,
        company_name=job.company_name,
        status=app.status,
        column=board.column_of(app.status),
        position=app.kanban_position,
        channel=app.channel,
        contact_email=app.contact_email,
        match_score=score,
        sent_at=app.sent_at,
        last_reply_at=app.last_reply_at,
        follow_up_at=app.follow_up_at,
        follow_up_due=bool(
            app.status == S.APPLIED and app.follow_up_at and app.follow_up_at <= now
        ),
        follow_up_count=app.follow_up_count,
        updated_at=app.updated_at,
    )


async def _cards(
    db: AsyncSession, user: User, application_id: uuid.UUID | None = None
) -> list[BoardCard]:
    key = await job_service.active_resume_key(db, user)
    stmt = (
        select(Application, Job, JobMatch.overall_score)
        .join(Job, Job.id == Application.job_id)
        .outerjoin(
            JobMatch,
            and_(
                JobMatch.job_id == Job.id,
                JobMatch.resume_id == key[0],
                JobMatch.profile_version == key[1],
            )
            if key
            else JobMatch.id.is_(None),
        )
        .where(Application.user_id == user.id)
        .order_by(Application.kanban_position, Application.updated_at.desc())
    )
    if application_id is not None:
        stmt = stmt.where(Application.id == application_id)
    now = datetime.now(UTC)
    return [_card(a, j, s, now) for a, j, s in (await db.execute(stmt.limit(500))).all()]


async def board_cards(db: AsyncSession, user: User) -> list[BoardCard]:
    return await _cards(db, user)


async def _has_drafts(db: AsyncSession, app_id: uuid.UUID) -> bool:
    found = await db.scalar(select(exists().where(ApplicationDraft.application_id == app_id)))
    return bool(found)


async def _position(db: AsyncSession, user: User, body: MoveIn) -> float:
    ids = [i for i in (body.before_id, body.after_id) if i is not None]
    rows = (
        dict(
            (
                await db.execute(
                    select(Application.id, Application.kanban_position).where(
                        Application.user_id == user.id, Application.id.in_(ids)
                    )
                )
            ).all()
        )
        if ids
        else {}
    )
    before = rows.get(body.before_id) if body.before_id else None
    after = rows.get(body.after_id) if body.after_id else None
    return board.position_between(before, after)


async def move(db: AsyncSession, user: User, application_id: uuid.UUID, body: MoveIn) -> BoardCard:
    """Drop a card into a column (and/or reorder it). Status side effects match the column."""
    app = await application_service.get_owned(db, user, application_id)
    if application_service._is_generating(app) and board.column_of(app.status) != body.column:
        raise Conflict("Drafts are still being written; move it when they're ready.")
    previous = app.status
    target = board.target_status(body.column, previous, withdrawn=body.withdrawn)
    if target == S.SAVED and await _has_drafts(db, app.id):
        target = S.READY
    now = datetime.now(UTC)

    if target != previous:
        if target in board.APPLIED_OR_LATER and previous not in board.APPLIED_OR_LATER:
            # Applying by drag: same rule as the Apply button about unchecked claims.
            out = await application_service.to_out(db, app)
            if out.flags_blocked and app.guardrail_flags_acknowledged_at is None:
                raise application_service.FlagsNotAcknowledged(
                    "Fix or confirm the flagged claims before marking as applied."
                )
            app.sent_at = app.sent_at or now
            if app.channel == ApplicationChannel.NONE:
                app.channel = ApplicationChannel.SITE
        if target == S.APPLIED:
            app.follow_up_at = app.follow_up_at or now + timedelta(days=user.follow_up_days)
        elif target in board.AFTER_APPLY:
            app.follow_up_at = None  # they answered (or it's over): no reminder
        if target == S.REPLIED and app.last_reply_at is None:
            app.last_reply_at = now
        if target in (S.SAVED, S.READY):
            app.sent_at = None
            app.follow_up_at = None
        app.status = target
        record_event(db, app, target, EventActor.USER, "Moved on the board", from_status=previous)
    app.kanban_position = await _position(db, user, body)
    app.updated_at = now
    await db.commit()
    return (await _cards(db, user, app.id))[0]


# --- follow-ups ----------------------------------------------------------------------------


async def request_follow_up_draft(
    db: AsyncSession, user: User, application_id: uuid.UUID, tone: Tone
) -> None:
    from app.tasks.application_tasks import write_follow_up

    app = await application_service.get_owned(db, user, application_id)
    if app.status not in board.APPLIED_OR_LATER:
        raise NotAppliedYet("Follow-ups are for applications you've already sent.")
    try:
        write_follow_up.delay(str(app.id), tone.value)
    except Exception as exc:
        raise ServiceUnavailable("Couldn't start writing. Try again in a moment.") from exc


async def follow_up_sent(db: AsyncSession, user: User, application_id: uuid.UUID) -> BoardCard:
    """The user sent a follow-up: count it and schedule the next reminder (at most two)."""
    app = await application_service.get_owned(db, user, application_id)
    if app.status != S.APPLIED:
        raise NotAppliedYet("Only applications waiting for a reply get follow-ups.")
    now = datetime.now(UTC)
    app.follow_up_count += 1
    app.follow_up_at = (
        now + timedelta(days=user.follow_up_days) if app.follow_up_count < MAX_FOLLOW_UPS else None
    )
    record_event(
        db, app, app.status, EventActor.USER, f"Follow-up {app.follow_up_count} sent",
        from_status=app.status,
    )  # fmt: skip
    await db.commit()
    return (await _cards(db, user, app.id))[0]


# --- notifications -------------------------------------------------------------------------


async def sync_follow_up_reminders(db: AsyncSession, user: User) -> int:
    """Create a reminder for each application whose follow-up date has passed (once each).

    Runs when the user opens notifications or the board, so reminders work without a
    scheduler; the beat task calls the same logic when one is running.
    """
    now = datetime.now(UTC)
    link = func.concat("/applications/", cast(Application.id, Notification.link.type))
    reminded = exists().where(
        Notification.user_id == user.id,
        Notification.kind == NotificationKind.FOLLOW_UP_DUE,
        Notification.link == link,
        Notification.created_at >= Application.follow_up_at,
    )
    rows = (
        await db.execute(
            select(Application, Job)
            .join(Job, Job.id == Application.job_id)
            .where(
                Application.user_id == user.id,
                Application.status == S.APPLIED,
                Application.follow_up_at.is_not(None),
                Application.follow_up_at <= now,
                ~reminded,
            )
            .limit(50)
        )
    ).all()
    for app, job in rows:
        db.add(
            Notification(
                user_id=user.id,
                kind=NotificationKind.FOLLOW_UP_DUE,
                title=f"Follow up with {job.company_name}",
                body=f"No reply yet for {job.title}. A short, polite follow-up often helps.",
                link=f"/applications/{app.id}",
            )
        )
    if rows:
        await db.commit()
    return len(rows)


async def notifications(db: AsyncSession, user: User, limit: int = 30) -> NotificationsOut:
    await sync_follow_up_reminders(db, user)
    items = (
        await db.scalars(
            select(Notification)
            .where(Notification.user_id == user.id)
            .order_by(Notification.created_at.desc())
            .limit(limit)
        )
    ).all()
    unread = await db.scalar(
        select(func.count())
        .select_from(Notification)
        .where(Notification.user_id == user.id, Notification.read_at.is_(None))
    )
    return NotificationsOut(
        items=[
            NotificationOut(
                id=n.id,
                kind=n.kind,
                title=n.title,
                body=n.body,
                link=n.link,
                read=n.read_at is not None,
                created_at=n.created_at,
            )
            for n in items
        ],
        unread=int(unread or 0),
    )


async def mark_read(db: AsyncSession, user: User, ids: list[uuid.UUID] | None) -> None:
    stmt = (
        update(Notification)
        .where(Notification.user_id == user.id, Notification.read_at.is_(None))
        .values(read_at=datetime.now(UTC))
    )
    if ids is not None:
        stmt = stmt.where(Notification.id.in_(ids))
    await db.execute(stmt)
    await db.commit()


# --- dashboard -----------------------------------------------------------------------------


def _week_start(d: date) -> date:
    return d - timedelta(days=d.weekday())


async def dashboard(db: AsyncSession, user: User, days: int) -> DashboardOut:
    since = datetime.now(UTC) - timedelta(days=days)
    key = await job_service.active_resume_key(db, user)

    jobs_found = await db.scalar(
        select(func.count())
        .select_from(UserJob)
        .where(UserJob.user_id == user.id, UserJob.discovered_at >= since)
    )
    avg_score = None
    gaps: list[SkillGap] = []
    if key:
        current = (
            JobMatch.user_id == user.id,
            JobMatch.resume_id == key[0],
            JobMatch.profile_version == key[1],
            JobMatch.stage == MatchStage.SCORED,
        )
        avg_score = await db.scalar(select(func.avg(JobMatch.overall_score)).where(*current))
        missing = (
            await db.scalars(
                select(JobMatch.missing_skills).where(
                    *current, JobMatch.overall_score >= GOOD_MATCH
                )
            )
        ).all()
        counts = Counter(skill for skills in missing for skill in dict.fromkeys(skills))
        gaps = [SkillGap(skill=s, jobs=n) for s, n in counts.most_common(10)]

    apps = (
        await db.execute(
            select(Application.status, Application.sent_at, Application.created_at).where(
                Application.user_id == user.id
            )
        )
    ).all()
    in_range = [a for a in apps if (a.sent_at or a.created_at) >= since]
    applied = [a for a in in_range if a.status in board.APPLIED_OR_LATER]
    replied = [a for a in applied if a.status in (S.REPLIED, S.INTERVIEW, S.OFFER)]
    interviews = [a for a in applied if a.status in (S.INTERVIEW, S.OFFER)]
    offers = [a for a in applied if a.status == S.OFFER]
    stats = StatCards(
        jobs_found=int(jobs_found or 0),
        avg_match_score=round(float(avg_score), 1) if avg_score is not None else None,
        applied=len(applied),
        replied=len(replied),
        reply_rate=round(len(replied) / len(applied), 3) if applied else None,
        interviews=len(interviews),
        offers=len(offers),
    )
    funnel = [
        FunnelStep(step="Found", count=stats.jobs_found),
        FunnelStep(step="Saved or prepared", count=len(in_range)),
        FunnelStep(step="Applied", count=len(applied)),
        FunnelStep(step="Replied", count=len(replied)),
        FunnelStep(step="Interview", count=len(interviews)),
        FunnelStep(step="Offer", count=len(offers)),
    ]
    return DashboardOut(
        days=days,
        stats=stats,
        funnel=funnel,
        missing_skills=gaps,
        weekly=await _weekly(db, user),
    )


async def _weekly(db: AsyncSession, user: User, weeks: int = 8) -> list[WeekPoint]:
    """Moves into applied / replied / interview per week, from the status history."""
    start = _week_start(datetime.now(UTC).date()) - timedelta(weeks=weeks - 1)
    day = cast(ApplicationEvent.created_at, Date)
    rows = (
        await db.execute(
            select(day, ApplicationEvent.to_status, func.count())
            .join(Application, Application.id == ApplicationEvent.application_id)
            .where(
                Application.user_id == user.id,
                ApplicationEvent.created_at >= datetime.combine(start, datetime.min.time(), UTC),
                ApplicationEvent.to_status.in_([S.APPLIED, S.REPLIED, S.INTERVIEW]),
                ApplicationEvent.from_status.is_distinct_from(ApplicationEvent.to_status),
            )
            .group_by(day, ApplicationEvent.to_status)
        )
    ).all()
    buckets: dict[date, dict[str, int]] = {
        start + timedelta(weeks=i): {"applied": 0, "replied": 0, "interviews": 0}
        for i in range(weeks)
    }
    names: dict[Any, str] = {S.APPLIED: "applied", S.REPLIED: "replied", S.INTERVIEW: "interviews"}
    for d, status, n in rows:
        bucket = buckets.get(_week_start(d))
        if bucket is not None:
            bucket[names[status]] += int(n)
    return [WeekPoint(week_start=w, **v) for w, v in buckets.items()]


async def get_card(db: AsyncSession, user: User, application_id: uuid.UUID) -> BoardCard:
    cards = await _cards(db, user, application_id)
    if not cards:
        raise NotFound("Application not found")
    return cards[0]
