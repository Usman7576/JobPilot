from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Request, Response, status

from app.core.cookies import clear_session_cookies
from app.core.deps import CurrentUser, DbSession
from app.core.ratelimit import limiter
from app.schemas.answers import AnswerItem, AnswersIn, AnswersOut
from app.schemas.auth import DeleteAccountIn, UserOut, UserUpdate
from app.services import account_service, user_service

router = APIRouter(prefix="/users", tags=["users"])


@router.get("/me")
async def get_me(user: CurrentUser) -> UserOut:
    return user_service.to_user_out(user)


@router.patch("/me")
async def update_me(body: UserUpdate, user: CurrentUser, db: DbSession) -> UserOut:
    updated = await user_service.update_user(db, user, body)
    return user_service.to_user_out(updated)


@router.get("/me/answers")
async def get_answers(user: CurrentUser) -> AnswersOut:
    """Your saved answers to common application-form questions (stored encrypted)."""
    return AnswersOut(items=[AnswerItem.model_validate(a) for a in user.answer_bank or []])


@router.put("/me/answers")
async def save_answers(body: AnswersIn, user: CurrentUser, db: DbSession) -> AnswersOut:
    user.answer_bank = [item.model_dump() for item in body.items]
    await db.commit()
    return AnswersOut(items=body.items)


@router.get(
    "/me/export",
    response_class=Response,
    responses={200: {"content": {"application/zip": {}}, "description": "Your data as a zip"}},
)
@limiter.limit("5/hour")
async def export_my_data(request: Request, user: CurrentUser, db: DbSession) -> Response:
    """Download everything stored about you (JSON files + your resume files)."""
    data = await account_service.export_zip(db, user)
    name = f"jobpilot-export-{datetime.now(UTC):%Y%m%d}.zip"
    return Response(
        data,
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="{name}"',
            "Cache-Control": "no-store",
        },
    )


@router.delete("/me", status_code=status.HTTP_204_NO_CONTENT)
@limiter.limit("5/hour")
async def delete_me(
    request: Request, response: Response, body: DeleteAccountIn, user: CurrentUser, db: DbSession
) -> None:
    """Delete your account and all your data. Type DELETE to confirm; this can't be undone."""
    await account_service.request_deletion(db, user, body.confirm)
    clear_session_cookies(response)
