from __future__ import annotations

import uuid
from urllib.parse import quote

from fastapi import APIRouter, File, Request, Response, UploadFile, status

from app.core.config import get_settings
from app.core.deps import CurrentUser, DbSession
from app.core.ratelimit import limiter
from app.schemas.profile import ResumeProfile
from app.schemas.resume import ResumeLabelIn, ResumeOut, ResumeSummary
from app.services import resume_service

router = APIRouter(prefix="/resumes", tags=["resumes"])


@router.post("", status_code=status.HTTP_202_ACCEPTED)
@limiter.limit("10/hour")
async def upload_resume(
    request: Request, user: CurrentUser, db: DbSession, file: UploadFile = File(...)
) -> ResumeOut:
    """Upload a PDF or DOCX. Parsing runs in the background; poll GET /resumes/{id}."""
    limit = get_settings().max_upload_mb * 1024 * 1024
    data = await file.read(limit + 1)
    resume = await resume_service.upload(db, user, filename=file.filename, data=data)
    return resume_service.to_out(resume)


@router.get("")
async def list_resumes(user: CurrentUser, db: DbSession) -> list[ResumeSummary]:
    return [resume_service.to_summary(r) for r in await resume_service.list_resumes(db, user)]


@router.get("/active")
async def get_active_resume(user: CurrentUser, db: DbSession) -> ResumeOut | None:
    resume = await resume_service.active_resume(db, user)
    return resume_service.to_out(resume) if resume else None


@router.get("/{resume_id}")
async def get_resume(resume_id: uuid.UUID, user: CurrentUser, db: DbSession) -> ResumeOut:
    return resume_service.to_out(await resume_service.get_owned(db, user, resume_id))


@router.put("/{resume_id}/profile")
async def update_profile(
    resume_id: uuid.UUID, body: ResumeProfile, user: CurrentUser, db: DbSession
) -> ResumeOut:
    """Save the user's edits. Bumps profile_version, which invalidates cached match scores."""
    resume = await resume_service.get_owned(db, user, resume_id)
    return resume_service.to_out(await resume_service.update_profile(db, user, resume, body))


@router.patch("/{resume_id}")
async def update_label(
    resume_id: uuid.UUID, body: ResumeLabelIn, user: CurrentUser, db: DbSession
) -> ResumeSummary:
    resume = await resume_service.get_owned(db, user, resume_id)
    resume.label = (body.label or "").strip()[:80] or None
    await db.commit()
    await db.refresh(resume)
    return resume_service.to_summary(resume)


@router.post("/{resume_id}/activate")
async def activate_resume(resume_id: uuid.UUID, user: CurrentUser, db: DbSession) -> ResumeSummary:
    resume = await resume_service.get_owned(db, user, resume_id)
    return resume_service.to_summary(await resume_service.activate(db, user, resume))


@router.post("/{resume_id}/reparse", status_code=status.HTTP_202_ACCEPTED)
@limiter.limit("10/hour")
async def reparse_resume(
    request: Request, resume_id: uuid.UUID, user: CurrentUser, db: DbSession
) -> ResumeSummary:
    resume = await resume_service.get_owned(db, user, resume_id)
    return resume_service.to_summary(await resume_service.reparse(db, resume))


@router.get(
    "/{resume_id}/file",
    response_class=Response,
    responses={200: {"content": {"application/pdf": {}, "application/octet-stream": {}}}},
)
async def download_resume_file(resume_id: uuid.UUID, user: CurrentUser, db: DbSession) -> Response:
    resume = await resume_service.get_owned(db, user, resume_id)
    data = await resume_service.read_file(resume)
    return Response(
        content=data,
        media_type=resume.mime_type,
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{quote(resume.file_name)}",
            "Cache-Control": "no-store",
        },
    )


@router.delete("/{resume_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_resume(resume_id: uuid.UUID, user: CurrentUser, db: DbSession) -> None:
    resume = await resume_service.get_owned(db, user, resume_id)
    await resume_service.delete(db, user, resume)
