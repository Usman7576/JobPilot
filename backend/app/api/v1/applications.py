from __future__ import annotations

import uuid

from fastapi import APIRouter, Request, status

from app.core.deps import CurrentUser, DbSession
from app.core.ratelimit import limiter
from app.schemas.application import (
    ApplicationListItem,
    ApplicationOut,
    ApplicationPatch,
    MarkAppliedIn,
    RegenerateIn,
    UseDraftIn,
)
from app.services import application_service

router = APIRouter(prefix="/applications", tags=["applications"])


@router.get("")
async def list_applications(user: CurrentUser, db: DbSession) -> list[ApplicationListItem]:
    return await application_service.list_for_user(db, user)


@router.get("/{application_id}")
async def get_application(
    application_id: uuid.UUID, user: CurrentUser, db: DbSession
) -> ApplicationOut:
    app = await application_service.get_owned(db, user, application_id)
    return await application_service.to_out(db, app)


@router.patch("/{application_id}")
async def update_application(
    application_id: uuid.UUID, body: ApplicationPatch, user: CurrentUser, db: DbSession
) -> ApplicationOut:
    """Edit the email, cover letter, contact or notes. The fast fact checks re-run on save."""
    return await application_service.patch(db, user, application_id, body)


@router.post("/{application_id}/regenerate", status_code=status.HTTP_202_ACCEPTED)
@limiter.limit("20/hour")
async def regenerate_draft(
    request: Request,
    application_id: uuid.UUID,
    body: RegenerateIn,
    user: CurrentUser,
    db: DbSession,
) -> ApplicationOut:
    """Write a new version of one draft (kept alongside the old ones)."""
    return await application_service.regenerate(db, user, application_id, body)


@router.post("/{application_id}/verify", status_code=status.HTTP_202_ACCEPTED)
@limiter.limit("20/hour")
async def verify_application(
    request: Request, application_id: uuid.UUID, user: CurrentUser, db: DbSession
) -> None:
    """Run the AI fact-check again (after editing)."""
    await application_service.reverify(db, user, application_id)


@router.post("/{application_id}/use-version")
async def use_draft_version(
    application_id: uuid.UUID, body: UseDraftIn, user: CurrentUser, db: DbSession
) -> ApplicationOut:
    return await application_service.use_version(db, user, application_id, body.draft_id)


@router.post("/{application_id}/acknowledge-flags")
async def acknowledge_flags(
    application_id: uuid.UUID, user: CurrentUser, db: DbSession
) -> ApplicationOut:
    """Confirm that flagged claims are accurate (needed before copying or marking applied)."""
    return await application_service.acknowledge_flags(db, user, application_id)


@router.post("/{application_id}/mark-applied")
async def mark_applied(
    application_id: uuid.UUID, body: MarkAppliedIn, user: CurrentUser, db: DbSession
) -> ApplicationOut:
    return await application_service.mark_applied(db, user, application_id, body.channel)


@router.delete("/{application_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_application(application_id: uuid.UUID, user: CurrentUser, db: DbSession) -> None:
    await application_service.delete(db, user, application_id)
