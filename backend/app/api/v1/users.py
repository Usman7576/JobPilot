from __future__ import annotations

from fastapi import APIRouter

from app.core.deps import CurrentUser, DbSession
from app.schemas.auth import UserOut, UserUpdate
from app.services import user_service

router = APIRouter(prefix="/users", tags=["users"])


@router.get("/me")
async def get_me(user: CurrentUser) -> UserOut:
    return user_service.to_user_out(user)


@router.patch("/me")
async def update_me(body: UserUpdate, user: CurrentUser, db: DbSession) -> UserOut:
    updated = await user_service.update_user(db, user, body)
    return user_service.to_user_out(updated)
