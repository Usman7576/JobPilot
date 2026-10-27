"""The user's discovered jobs: list with filters, detail, dismiss."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import Select, and_, exists, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import NotFound
from app.models import Job, JobSourceRecord, User, UserJob
from app.models.enums import RemoteType
from app.providers.sources import all_sources
from app.schemas.job import JobCard, JobDetail, JobPage, JobSort, JobSourceLink

SNIPPET_CHARS = 280


def _snippet(text: str | None) -> str | None:
    if not text:
        return None
    flat = " ".join(text.split())
    return flat if len(flat) <= SNIPPET_CHARS else flat[:SNIPPET_CHARS].rsplit(" ", 1)[0] + "…"


def _card(job: Job, user_job: UserJob, sources: list[str]) -> JobCard:
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
        required_skills=job.required_skills,
        snippet=_snippet(job.description_text),
        posted_at=job.posted_at,
        discovered_at=user_job.discovered_at,
        sources=sources,
        url=job.primary_url,
        apply_url=job.apply_url,
        has_contact_email=bool(job.contact_emails),
        dismissed=user_job.dismissed_at is not None,
    )


async def list_jobs(
    db: AsyncSession,
    user: User,
    *,
    q: str | None,
    source: str | None,
    remote_type: RemoteType | None,
    posted_within_days: int | None,
    include_dismissed: bool,
    sort: JobSort,
    limit: int,
    offset: int,
) -> JobPage:
    stmt: Select[Job, UserJob] = (
        select(Job, UserJob)
        .join(UserJob, UserJob.job_id == Job.id)
        .where(UserJob.user_id == user.id)
    )
    if not include_dismissed:
        stmt = stmt.where(UserJob.dismissed_at.is_(None))
    if q:
        like = f"%{q.strip()}%"
        stmt = stmt.where(or_(Job.title.ilike(like), Job.company_name.ilike(like)))
    if source:
        stmt = stmt.where(
            exists().where(and_(JobSourceRecord.job_id == Job.id, JobSourceRecord.source == source))
        )
    if remote_type:
        stmt = stmt.where(Job.remote_type == remote_type)
    if posted_within_days:
        cutoff = datetime.now(UTC) - timedelta(days=posted_within_days)
        stmt = stmt.where(func.coalesce(Job.posted_at, UserJob.discovered_at) >= cutoff)

    total = await db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    order = (
        func.coalesce(Job.posted_at, UserJob.discovered_at).desc()
        if sort == "posted"
        else UserJob.discovered_at.desc()
    )
    rows = (await db.execute(stmt.order_by(order, Job.id).limit(limit).offset(offset))).all()

    sources_by_job: dict[uuid.UUID, list[str]] = {}
    if rows:
        src_rows = await db.execute(
            select(JobSourceRecord.job_id, JobSourceRecord.source)
            .where(JobSourceRecord.job_id.in_([job.id for job, _ in rows]))
            .distinct()
        )
        for job_id, name in src_rows:
            sources_by_job.setdefault(job_id, []).append(name)

    items = [_card(job, uj, sorted(sources_by_job.get(job.id, []))) for job, uj in rows]
    return JobPage(items=items, total=total, has_more=offset + len(items) < total)


async def _owned(db: AsyncSession, user: User, job_id: uuid.UUID) -> tuple[Job, UserJob]:
    row = (
        await db.execute(
            select(Job, UserJob)
            .join(UserJob, UserJob.job_id == Job.id)
            .where(Job.id == job_id, UserJob.user_id == user.id)
        )
    ).first()
    if row is None:
        raise NotFound("Job not found")
    return row[0], row[1]


async def detail(db: AsyncSession, user: User, job_id: uuid.UUID) -> JobDetail:
    job, user_job = await _owned(db, user, job_id)
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
    card = _card(job, user_job, sorted({r.source for r in records}))
    return JobDetail(
        **card.model_dump(),
        description_text=job.description_text,
        contact_emails=job.contact_emails,
        source_links=links,
    )


async def set_dismissed(db: AsyncSession, user: User, job_id: uuid.UUID, dismissed: bool) -> None:
    _, user_job = await _owned(db, user, job_id)
    user_job.dismissed_at = datetime.now(UTC) if dismissed else None
    await db.commit()
