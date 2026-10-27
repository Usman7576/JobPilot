from __future__ import annotations

from fastapi import APIRouter

from app.core.deps import CurrentUser, DbSession
from app.schemas.preference import PreferencesIn, PreferencesOut, SourceOut
from app.schemas.profile import ResumeProfile
from app.services import preference_service, resume_service

router = APIRouter(tags=["preferences"])


@router.get("/preferences")
async def get_preferences(user: CurrentUser, db: DbSession) -> PreferencesOut:
    """Saved preferences, or suggested defaults (titles from the active resume)."""
    active = await resume_service.active_resume(db, user)
    roles: list[str] = []
    if active is not None and active.profile:
        roles = ResumeProfile.model_validate(active.profile).preferred_roles
    return await preference_service.get(db, user, roles)


@router.put("/preferences")
async def save_preferences(body: PreferencesIn, user: CurrentUser, db: DbSession) -> PreferencesOut:
    return await preference_service.save(db, user, body)


@router.get("/sources")
async def list_sources(user: CurrentUser) -> list[SourceOut]:
    """Every job source, whether its key is configured, and whether it's paused."""
    return preference_service.list_sources()
