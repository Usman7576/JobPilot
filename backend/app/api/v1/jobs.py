from __future__ import annotations

import uuid

from fastapi import APIRouter, Query, status

from app.core.deps import CurrentUser, DbSession
from app.models.enums import PayStatus, RemoteType, SearchKind
from app.schemas.job import JobDetail, JobPage, JobSort
from app.services import job_service

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
    include_dismissed: bool = False,
    sort: JobSort = "posted",
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
