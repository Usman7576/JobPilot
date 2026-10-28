from __future__ import annotations

from fastapi import APIRouter, status

from app.core.deps import CurrentUser, DbSession
from app.schemas.tracking import MarkReadIn, NotificationsOut
from app.services import tracking_service

router = APIRouter(prefix="/notifications", tags=["notifications"])


@router.get("")
async def list_notifications(user: CurrentUser, db: DbSession) -> NotificationsOut:
    """Latest notifications (follow-up reminders are created here when they're due)."""
    return await tracking_service.notifications(db, user)


@router.post("/read", status_code=status.HTTP_204_NO_CONTENT)
async def mark_read(body: MarkReadIn, user: CurrentUser, db: DbSession) -> None:
    await tracking_service.mark_read(db, user, body.ids)
