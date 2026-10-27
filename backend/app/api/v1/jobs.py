from __future__ import annotations

import uuid

from fastapi import APIRouter, Query, Request, status

from app.core.deps import CurrentUser, DbSession
from app.core.ratelimit import limiter
from app.models.enums import PayStatus, Recommendation, RemoteType, SearchKind
from app.schemas.application import ApplicationOut, PrepareIn
from app.schemas.job import JobDetail, JobPage, JobSort
from app.services import application_service, job_service

router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.get("")
async def list_jobs(
    user: CurrentUser,
    db: DbSession,
    q: str | None = Query(default=None, max_length=100),
    kind: SearchKind | None = None,
    pay: PayStatus | None = None,
    source: str | None = Query(default=None, max_length=40),
    remote_type: RemoteType | None = None,
    posted_within_days: int | None = Query(default=None, ge=1, le=90),
    min_score: int | None = Query(default=None, ge=0, le=100),
    recommendation: Recommendation | None = None,
    include_filtered: bool = False,
    include_dismissed: bool = False,
    sort: JobSort = "score",
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> JobPage:
    return await job_service.list_jobs(
        db,
        user,
        q=q,
        kind=kind,
        pay=pay,
        source=source,
        remote_type=remote_type,
        posted_within_days=posted_within_days,
        min_score=min_score,
        recommendation=recommendation,
        include_filtered=include_filtered,
        include_dismissed=include_dismissed,
        sort=sort,
        limit=limit,
        offset=offset,
    )


@router.get("/{job_id}")
async def get_job(job_id: uuid.UUID, user: CurrentUser, db: DbSession) -> JobDetail:
    return await job_service.detail(db, user, job_id)


@router.post("/{job_id}/dismiss", status_code=status.HTTP_204_NO_CONTENT)
async def dismiss_job(job_id: uuid.UUID, user: CurrentUser, db: DbSession) -> None:
    await job_service.set_dismissed(db, user, job_id, True)


@router.post("/{job_id}/undismiss", status_code=status.HTTP_204_NO_CONTENT)
async def undismiss_job(job_id: uuid.UUID, user: CurrentUser, db: DbSession) -> None:
    await job_service.set_dismissed(db, user, job_id, False)


@router.post("/{job_id}/rescore", status_code=status.HTTP_202_ACCEPTED)
@limiter.limit("20/hour")
async def rescore_job(
    request: Request, job_id: uuid.UUID, user: CurrentUser, db: DbSession
) -> None:
    """Score this job again against your current resume (uses one AI request)."""
    await job_service.rescore(db, user, job_id)


@router.post("/{job_id}/prepare-application", status_code=status.HTTP_202_ACCEPTED)
@limiter.limit("20/hour")
async def prepare_application(
    request: Request, job_id: uuid.UUID, body: PrepareIn, user: CurrentUser, db: DbSession
) -> ApplicationOut:
    """Find a contact and write an email + cover letter in the background; poll the result."""
    return await application_service.prepare(db, user, job_id, body)


@router.post("/{job_id}/save")
async def save_job(job_id: uuid.UUID, user: CurrentUser, db: DbSession) -> ApplicationOut:
    """Save for later (an application in "saved", with no drafts yet)."""
    return await application_service.save_for_later(db, user, job_id)
