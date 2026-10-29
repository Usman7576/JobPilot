"""The user's discovered jobs: ranked feed with filters, detail with the match, dismiss."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import Select, and_, exists, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import AppError, NotFound, ServiceUnavailable
from app.models import Application, Job, JobMatch, JobSourceRecord, Resume, User, UserJob
from app.models.enums import (
    ApplicationStatus,
    EmploymentType,
    PayStatus,
    Recommendation,
    RemoteType,
    ResumeStatus,
    SearchKind,
)
from app.providers.sources import all_sources
from app.schemas.application import ApplicationRef
from app.schemas.job import JobCard, JobDetail, JobPage, JobSort, JobSourceLink
from app.schemas.match import MatchDetail, MatchSummary, RedFlagOut

SNIPPET_CHARS = 280
# Sent (or on its way): "hide applied" leaves these out of the feed.
SENT_OR_LATER = (
    ApplicationStatus.QUEUED,
    ApplicationStatus.APPLIED,
    ApplicationStatus.REPLIED,
    ApplicationStatus.INTERVIEW,
    ApplicationStatus.OFFER,
    ApplicationStatus.REJECTED,
    ApplicationStatus.WITHDRAWN,
)


class NoActiveResume(AppError):
    status_code, code, title = 422, "no_active_resume", "Upload a resume first"


def _snippet(text: str | None) -> str | None:
    if not text:
        return None
    flat = " ".join(text.split())
    return flat if len(flat) <= SNIPPET_CHARS else flat[:SNIPPET_CHARS].rsplit(" ", 1)[0] + "…"


def _summary(match: JobMatch | None) -> MatchSummary | None:
    if match is None:
        return None
    return MatchSummary(
        stage=match.stage,
        overall_score=match.overall_score,
        recommendation=match.recommendation,
        similarity=round(match.similarity, 3) if match.similarity is not None else None,
        hard_filter_passed=match.hard_filter_passed,
        hard_filter_reasons=match.hard_filter_reasons,
    )


def _detail(match: JobMatch | None) -> MatchDetail | None:
    summary = _summary(match)
    if match is None or summary is None:
        return None
    return MatchDetail(
        **summary.model_dump(),
        breakdown=match.breakdown,
        matched_skills=match.matched_skills,
        missing_skills=match.missing_skills,
        red_flags=[RedFlagOut.model_validate(f) for f in match.red_flags],
        why_good_fit=match.why_good_fit,
        failure_reason=match.failure_reason,
        scored_at=match.scored_at,
    )


def _card(job: Job, user_job: UserJob, sources: list[str], match: JobMatch | None) -> JobCard:
    return JobCard(
        id=job.id,
        title=job.title,
        company_name=job.company_name,
        location_raw=job.location_raw,
        remote_type=job.remote_type,
        employment_type=job.employment_type,
        seniority=job.seniority,
        min_years_experience=(
            float(job.min_years_experience) if job.min_years_experience is not None else None
        ),
        salary_min=job.salary_min,
        salary_max=job.salary_max,
        salary_currency=job.salary_currency,
        salary_period=job.salary_period,
        pay_status=job.pay_status,
        required_skills=job.required_skills,
        snippet=_snippet(job.description_text),
        posted_at=job.posted_at,
        discovered_at=user_job.discovered_at,
        sources=sources,
        url=job.primary_url,
        apply_url=job.apply_url,
        has_contact_email=bool(job.contact_emails),
        dismissed=user_job.dismissed_at is not None,
        match=_summary(match),
    )


async def active_resume_key(db: AsyncSession, user: User) -> tuple[uuid.UUID, int] | None:
    row = (
        await db.execute(
            select(Resume.id, Resume.profile_version).where(
                Resume.user_id == user.id,
                Resume.is_active.is_(True),
                Resume.status == ResumeStatus.PARSED,
            )
        )
    ).first()
    return (row[0], row[1]) if row else None


def _match_join(key: tuple[uuid.UUID, int] | None) -> Any:
    """Join condition for the match of the user's current resume version (if any)."""
    if key is None:
        return JobMatch.id.is_(None)  # never true: no resume means no match
    return and_(
        JobMatch.job_id == Job.id,
        JobMatch.resume_id == key[0],
        JobMatch.profile_version == key[1],
    )


async def list_jobs(
    db: AsyncSession,
    user: User,
    *,
    q: str | None,
    kind: SearchKind | None,
    pay: PayStatus | None,
    source: str | None,
    remote_type: RemoteType | None,
    posted_within_days: int | None,
    min_score: int | None,
    recommendation: Recommendation | None,
    include_filtered: bool,
    include_dismissed: bool,
    sort: JobSort,
    limit: int,
    offset: int,
    has_email: bool = False,
    hide_applied: bool = False,
) -> JobPage:
    key = await active_resume_key(db, user)
    stmt: Select[Job, UserJob, JobMatch] = (
        select(Job, UserJob, JobMatch)
        .join(UserJob, UserJob.job_id == Job.id)
        .outerjoin(JobMatch, _match_join(key))
        .where(UserJob.user_id == user.id)
    )
    if not include_dismissed:
        stmt = stmt.where(UserJob.dismissed_at.is_(None))
    if q:
        like = f"%{q.strip()}%"
        stmt = stmt.where(or_(Job.title.ilike(like), Job.company_name.ilike(like)))
    if kind == SearchKind.INTERNSHIPS:
        stmt = stmt.where(Job.employment_type == EmploymentType.INTERNSHIP)
    elif kind == SearchKind.JOBS:
        stmt = stmt.where(Job.employment_type != EmploymentType.INTERNSHIP)
    if pay:
        stmt = stmt.where(Job.pay_status == pay)
    if source:
        stmt = stmt.where(
            exists().where(and_(JobSourceRecord.job_id == Job.id, JobSourceRecord.source == source))
        )
    if remote_type:
        stmt = stmt.where(Job.remote_type == remote_type)
    if posted_within_days:
        cutoff = datetime.now(UTC) - timedelta(days=posted_within_days)
        stmt = stmt.where(func.coalesce(Job.posted_at, UserJob.discovered_at) >= cutoff)
    if min_score is not None:
        stmt = stmt.where(JobMatch.overall_score >= min_score)
    if recommendation:
        stmt = stmt.where(JobMatch.recommendation == recommendation)
    if has_email:
        stmt = stmt.where(func.cardinality(Job.contact_emails) > 0)
    if hide_applied:
        stmt = stmt.where(
            ~exists().where(
                Application.user_id == user.id,
                Application.job_id == Job.id,
                Application.status.in_(SENT_OR_LATER),
            )
        )

    hidden = stmt.where(JobMatch.hard_filter_passed.is_(False))
    filtered_out = await db.scalar(select(func.count()).select_from(hidden.subquery())) or 0
    if not include_filtered:
        stmt = stmt.where(or_(JobMatch.id.is_(None), JobMatch.hard_filter_passed.is_(True)))

    total = await db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    posted = func.coalesce(Job.posted_at, UserJob.discovered_at).desc()
    order: list[Any]
    if sort == "score":
        order = [
            JobMatch.overall_score.desc().nulls_last(),
            JobMatch.similarity.desc().nulls_last(),
            posted,
        ]
    elif sort == "posted":
        order = [posted]
    else:
        order = [UserJob.discovered_at.desc()]
    rows = (await db.execute(stmt.order_by(*order, Job.id).limit(limit).offset(offset))).all()

    sources_by_job: dict[uuid.UUID, list[str]] = {}
    if rows:
        src_rows = await db.execute(
            select(JobSourceRecord.job_id, JobSourceRecord.source)
            .where(JobSourceRecord.job_id.in_([job.id for job, _, _ in rows]))
            .distinct()
        )
        for job_id, name in src_rows:
            sources_by_job.setdefault(job_id, []).append(name)

    apps: dict[uuid.UUID, ApplicationRef] = {}
    if rows:
        app_rows = await db.execute(
            select(Application.job_id, Application.id, Application.status).where(
                Application.user_id == user.id,
                Application.job_id.in_([job.id for job, _, _ in rows]),
            )
        )
        apps = {job_id: ApplicationRef(id=i, status=s) for job_id, i, s in app_rows}
    items = [
        _card(job, uj, sorted(sources_by_job.get(job.id, [])), m).model_copy(
            update={"application": apps.get(job.id)}
        )
        for job, uj, m in rows
    ]
    return JobPage(
        items=items,
        total=total,
        has_more=offset + len(items) < total,
        filtered_out=filtered_out,
        has_resume=key is not None,
    )


async def _owned(
    db: AsyncSession, user: User, job_id: uuid.UUID
) -> tuple[Job, UserJob, JobMatch | None]:
    key = await active_resume_key(db, user)
    row = (
        await db.execute(
            select(Job, UserJob, JobMatch)
            .join(UserJob, UserJob.job_id == Job.id)
            .outerjoin(JobMatch, _match_join(key))
            .where(Job.id == job_id, UserJob.user_id == user.id)
        )
    ).first()
    if row is None:
        raise NotFound("Job not found")
    return row[0], row[1], row[2]


async def detail(db: AsyncSession, user: User, job_id: uuid.UUID) -> JobDetail:
    job, user_job, match = await _owned(db, user, job_id)
    if user_job.viewed_at is None:
        user_job.viewed_at = datetime.now(UTC)
        await db.commit()
    records = (
        await db.scalars(select(JobSourceRecord).where(JobSourceRecord.job_id == job.id))
    ).all()
    registry = all_sources()
    links = [
        JobSourceLink(
            source=r.source,
            label=registry[r.source].info.label if r.source in registry else r.source,
            url=r.url,
        )
        for r in records
    ]
    card = _card(job, user_job, sorted({r.source for r in records}), match)
    return JobDetail(
        **card.model_dump(exclude={"match", "application"}),
        description_text=job.description_text,
        contact_emails=job.contact_emails,
        source_links=links,
        match=_detail(match),
        application=await _application_ref(db, user, job.id),
    )


async def _application_ref(
    db: AsyncSession, user: User, job_id: uuid.UUID
) -> ApplicationRef | None:
    row = (
        await db.execute(
            select(Application.id, Application.status).where(
                Application.user_id == user.id, Application.job_id == job_id
            )
        )
    ).first()
    return ApplicationRef(id=row[0], status=row[1]) if row else None


async def set_dismissed(db: AsyncSession, user: User, job_id: uuid.UUID, dismissed: bool) -> None:
    _, user_job, _ = await _owned(db, user, job_id)
    user_job.dismissed_at = datetime.now(UTC) if dismissed else None
    await db.commit()


async def rescore(db: AsyncSession, user: User, job_id: uuid.UUID) -> None:
    """Queue a fresh score for one job against the current resume version."""
    from app.services.resume_service import enqueue_match

    await _owned(db, user, job_id)
    if await active_resume_key(db, user) is None:
        raise NoActiveResume("Upload a resume to get match scores.")
    if not enqueue_match(user.id, [job_id]):
        raise ServiceUnavailable("Couldn't queue the rescore. Try again in a moment.")
