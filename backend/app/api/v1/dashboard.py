from __future__ import annotations

from fastapi import APIRouter, Query

from app.core.deps import CurrentUser, DbSession
from app.schemas.tracking import DashboardOut
from app.services import tracking_service

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("")
async def get_dashboard(
    user: CurrentUser, db: DbSession, days: int = Query(default=30, ge=7, le=365)
) -> DashboardOut:
    """Stat cards, funnel, top missing skills and weekly activity."""
    return await tracking_service.dashboard(db, user, days)
