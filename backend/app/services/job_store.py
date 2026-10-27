"""Persist normalized jobs with dedupe (by URL, then by company+title+location)."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import or_, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.domain.normalize import NormalizedJob
from app.models import Company, Job, JobSourceRecord, UserJob
from app.models.enums import NormalizationStatus


@dataclass(frozen=True)
class StoreResult:
    job_id: uuid.UUID
    created: bool  # a brand-new posting (not a duplicate)
    new_for_user: bool  # first time this user sees it


def _company(session: Session, job: NormalizedJob) -> uuid.UUID:
    stmt = (
        pg_insert(Company)
        .values(name=job.company_name, normalized_name=job.normalized_company)
        .on_conflict_do_nothing(index_elements=["normalized_name"])
    )
    session.execute(stmt)
    company_id = session.scalar(
        select(Company.id).where(Company.normalized_name == job.normalized_company)
    )
    assert company_id is not None
    return company_id


def store(
    session: Session, job: NormalizedJob, *, user_id: uuid.UUID, run_id: uuid.UUID
) -> StoreResult:
    now = datetime.now(UTC)
    existing = session.scalar(
        select(Job)
        .where(or_(Job.url_hash == job.url_hash, Job.dedupe_hash == job.dedupe_hash))
        .limit(1)
    )
    created = existing is None
    if existing is None:
        try:
            with session.begin_nested():
                existing = _insert(session, job, now)
        except IntegrityError:
            # Another search stored the same posting a moment ago.
            created = False
            existing = session.scalar(
                select(Job)
                .where(or_(Job.url_hash == job.url_hash, Job.dedupe_hash == job.dedupe_hash))
                .limit(1)
            )
            assert existing is not None
    else:
        _merge(existing, job, now)

    session.execute(
        pg_insert(JobSourceRecord)
        .values(
            job_id=existing.id,
            source=job.source,
            source_job_id=job.source_job_id,
            url=job.primary_url,
            raw=job.raw_meta,
            scraped_at=now,
        )
        .on_conflict_do_update(
            index_elements=["source", "source_job_id"],
            set_={"scraped_at": now, "job_id": existing.id},
        )
    )
    inserted = session.execute(
        pg_insert(UserJob)
        .values(user_id=user_id, job_id=existing.id, first_run_id=run_id, discovered_at=now)
        .on_conflict_do_nothing(index_elements=["user_id", "job_id"])
        .returning(UserJob.id)
    ).first()
    return StoreResult(job_id=existing.id, created=created, new_for_user=inserted is not None)


def _insert(session: Session, job: NormalizedJob, now: datetime) -> Job:
    row = Job(
        company_id=_company(session, job),
        company_name=job.company_name,
        title=job.title,
        normalized_title=job.normalized_title,
        location_raw=job.location_raw,
        location=job.location,
        remote_type=job.remote_type,
        employment_type=job.employment_type,
        seniority=job.seniority,
        min_years_experience=job.min_years_experience,
        salary_min=job.salary_min,
        salary_max=job.salary_max,
        salary_currency=job.salary_currency,
        salary_period=job.salary_period,
        required_skills=job.required_skills,
        nice_to_have_skills=[],
        description_text=job.description_text,
        contact_emails=job.contact_emails,
        primary_url=job.primary_url,
        apply_url=job.apply_url,
        url_hash=job.url_hash,
        dedupe_hash=job.dedupe_hash,
        posted_at=job.posted_at,
        first_seen_at=now,
        last_seen_at=now,
        normalization_status=NormalizationStatus.RULES_ONLY,
    )
    session.add(row)
    session.flush()
    return row


def _merge(existing: Job, job: NormalizedJob, now: datetime) -> None:
    existing.last_seen_at = now
    existing.is_active = True
    # Keep the richest version of the posting across sources.
    if job.description_text and len(job.description_text) > len(existing.description_text or ""):
        existing.description_text = job.description_text
        existing.required_skills = job.required_skills or existing.required_skills
        existing.embedding = None  # description changed: re-embed
    existing.apply_url = existing.apply_url or job.apply_url
    existing.contact_emails = list(dict.fromkeys(existing.contact_emails + job.contact_emails))[:5]
    if existing.salary_min is None and job.salary_min is not None:
        existing.salary_min, existing.salary_max = job.salary_min, job.salary_max
        existing.salary_currency, existing.salary_period = job.salary_currency, job.salary_period
    if existing.posted_at is None:
        existing.posted_at = job.posted_at
