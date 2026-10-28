from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Header, Request, status

from app.core.deps import CurrentUser, DbSession
from app.core.ratelimit import limiter
from app.schemas.application import (
    ApplicationListItem,
    ApplicationOut,
    ApplicationPatch,
    MarkAppliedIn,
    RegenerateIn,
    SendIn,
    SendQuotaOut,
    ToneIn,
    UseDraftIn,
)
from app.schemas.tracking import BoardCard, MoveIn
from app.services import application_service, send_service, tracking_service

router = APIRouter(prefix="/applications", tags=["applications"])


@router.get("")
async def list_applications(user: CurrentUser, db: DbSession) -> list[ApplicationListItem]:
    return await application_service.list_for_user(db, user)


@router.get("/board")
async def get_board(user: CurrentUser, db: DbSession) -> list[BoardCard]:
    """Every application as a board card (the client groups them by `column`)."""
    await tracking_service.sync_follow_up_reminders(db, user)
    return await tracking_service.board_cards(db, user)


@router.get("/send-quota")
async def send_quota(user: CurrentUser, db: DbSession) -> SendQuotaOut:
    """Today's emails: your daily limit, sent, waiting in the queue, and how many are left."""
    return await send_service.quota(db, user)


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


@router.post("/{application_id}/move")
async def move_application(
    application_id: uuid.UUID, body: MoveIn, user: CurrentUser, db: DbSession
) -> BoardCard:
    """Drag and drop on the board: change column (status) and/or order."""
    return await tracking_service.move(db, user, application_id, body)


@router.post("/{application_id}/follow-up-draft", status_code=status.HTTP_202_ACCEPTED)
@limiter.limit("20/hour")
async def follow_up_draft(
    request: Request, application_id: uuid.UUID, body: ToneIn, user: CurrentUser, db: DbSession
) -> None:
    """Write a short follow-up email (you send it yourself; poll the application)."""
    await tracking_service.request_follow_up_draft(db, user, application_id, body.tone)


@router.post("/{application_id}/follow-up-sent")
async def follow_up_sent(application_id: uuid.UUID, user: CurrentUser, db: DbSession) -> BoardCard:
    """You sent a follow-up: counts it and schedules the next reminder (two at most)."""
    return await tracking_service.follow_up_sent(db, user, application_id)


@router.post("/{application_id}/send", status_code=status.HTTP_202_ACCEPTED)
@limiter.limit("30/hour")
async def send_application(
    request: Request,
    application_id: uuid.UUID,
    body: SendIn,
    user: CurrentUser,
    db: DbSession,
    idempotency_key: Annotated[str, Header(min_length=8, max_length=200)],
) -> ApplicationOut:
    """Schedule the reviewed email to go from your Gmail in 30-120 s (cancellable until then).

    Needs `preview_confirmed: true` (set by the final preview) and an `Idempotency-Key`
    header; a retried request with the same key returns the same result.
    """
    return await send_service.send(
        db,
        user,
        application_id,
        idempotency_key=idempotency_key,
        preview_confirmed=body.preview_confirmed,
    )


@router.post("/{application_id}/cancel-send")
async def cancel_send(
    application_id: uuid.UUID, user: CurrentUser, db: DbSession
) -> ApplicationOut:
    """Stop a scheduled email before it goes (it returns to Ready)."""
    return await send_service.cancel(db, user, application_id)
