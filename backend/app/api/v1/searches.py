from __future__ import annotations

import uuid

from fastapi import APIRouter, Query, Request, status

from app.core.deps import CurrentUser, DbSession
from app.core.ratelimit import limiter
from app.schemas.search import SearchRunOut
from app.services import search_service

router = APIRouter(prefix="/searches", tags=["searches"])


@router.post("", status_code=status.HTTP_202_ACCEPTED)
@limiter.limit("6/hour")
async def start_search(request: Request, user: CurrentUser, db: DbSession) -> SearchRunOut:
    """Start a search with the saved preferences. 409 if one is already running."""
    return await search_service.start(db, user)


@router.get("")
async def list_searches(
    user: CurrentUser, db: DbSession, limit: int = Query(default=5, ge=1, le=20)
) -> list[SearchRunOut]:
    return await search_service.recent(db, user, limit)


@router.get("/active")
async def get_active_search(user: CurrentUser, db: DbSession) -> SearchRunOut | None:
    run = await search_service.active_run(db, user)
    return await search_service.get(db, user, run.id) if run else None


@router.get("/{run_id}")
async def get_search(run_id: uuid.UUID, user: CurrentUser, db: DbSession) -> SearchRunOut:
    return await search_service.get(db, user, run_id)


@router.post("/{run_id}/cancel")
async def cancel_search(run_id: uuid.UUID, user: CurrentUser, db: DbSession) -> SearchRunOut:
    return await search_service.cancel(db, user, run_id)
