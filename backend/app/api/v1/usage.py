from __future__ import annotations

from fastapi import APIRouter

from app.core.deps import CurrentUser, DbSession
from app.schemas.usage import UsageOut
from app.services import usage_service

router = APIRouter(prefix="/usage", tags=["usage"])


@router.get("")
async def get_usage(user: CurrentUser, db: DbSession) -> UsageOut:
    """Your AI requests this month, by feature and model, and today's free requests left."""
    return await usage_service.usage(db, user)
