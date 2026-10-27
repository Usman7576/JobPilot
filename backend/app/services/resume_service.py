"""API-side resume operations: upload, list, edit profile, activate, reparse, delete."""

from __future__ import annotations

import asyncio
import hashlib
import uuid
from decimal import Decimal

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import crypto
from app.core.config import get_settings
from app.core.errors import AppError, Conflict, NotFound, ServiceUnavailable
from app.core.logging import get_logger
from app.db.base import uuid7
from app.domain.profile import finalize_profile
from app.domain.text_extraction import MIME_TYPES, ExtractionError, pdf_page_count, sniff_kind
from app.models import Resume, User
from app.models.enums import OnboardingStep, ResumeStatus
from app.providers.storage import get_storage
from app.schemas.profile import ResumeProfile
from app.schemas.resume import ResumeOut, ResumeSummary

log = get_logger(__name__)


class InvalidUpload(AppError):
    status_code, code, title = 422, "invalid_upload", "This file can't be used"


class ResumeNotReady(AppError):
    status_code, code, title = 409, "resume_not_ready", "This resume hasn't been parsed yet"


def _split_error(error: str | None) -> tuple[str | None, str | None]:
    if not error:
        return None, None
    code, _, message = error.partition(": ")
    return code, message or None


def to_summary(resume: Resume) -> ResumeSummary:
    code, message = _split_error(resume.error)
    return ResumeSummary(
        id=resume.id,
        version=resume.version,
        label=resume.label,
        is_active=resume.is_active,
        status=resume.status,
        error_code=code,
        error_message=message,
        file_name=resume.file_name,
        mime_type=resume.mime_type,
        profile_version=resume.profile_version,
        total_years_experience=(
            float(resume.total_years_experience)
            if resume.total_years_experience is not None
            else None
        ),
        seniority=resume.seniority,
        skills_count=len(resume.skills_index or []),
        has_embedding=resume.embedding is not None,
        created_at=resume.created_at,
    )


def to_out(resume: Resume) -> ResumeOut:
    profile = ResumeProfile.model_validate(resume.profile) if resume.profile else None
    return ResumeOut(**to_summary(resume).model_dump(), profile=profile)


def _safe_filename(name: str | None) -> str:
    base = (name or "resume").replace("\\", "/").rsplit("/", 1)[-1]
    cleaned = "".join(c for c in base if c.isalnum() or c in " ._-()").strip() or "resume"
    return cleaned[:120]


async def get_owned(db: AsyncSession, user: User, resume_id: uuid.UUID) -> Resume:
    resume = await db.scalar(
        select(Resume).where(Resume.id == resume_id, Resume.user_id == user.id)
    )
    if resume is None:
        raise NotFound("Resume not found")
    return resume


async def list_resumes(db: AsyncSession, user: User) -> list[Resume]:
    rows = await db.scalars(
        select(Resume).where(Resume.user_id == user.id).order_by(Resume.version.desc())
    )
    return list(rows)


async def active_resume(db: AsyncSession, user: User) -> Resume | None:
    return await db.scalar(select(Resume).where(Resume.user_id == user.id, Resume.is_active))


def _enqueue_parse(resume_id: uuid.UUID) -> None:
    from app.tasks.resume_tasks import parse_resume

    try:
        parse_resume.delay(str(resume_id))
    except Exception as exc:  # broker down
        log.error("enqueue_failed", task="parse_resume", error_type=type(exc).__name__)
        raise ServiceUnavailable("Couldn't start parsing. Try again in a moment.") from exc


def _enqueue_embed(resume_id: uuid.UUID, profile_version: int) -> None:
    from app.tasks.resume_tasks import embed_resume

    try:
        embed_resume.delay(str(resume_id), profile_version)
    except Exception as exc:
        # Not fatal: the profile is saved; matching re-embeds missing vectors later.
        log.error("enqueue_failed", task="embed_resume", error_type=type(exc).__name__)


def enqueue_match(user_id: uuid.UUID, job_ids: list[uuid.UUID] | None = None) -> bool:
    from app.tasks.matching_tasks import match_jobs

    try:
        match_jobs.delay(str(user_id), [str(j) for j in job_ids] if job_ids else None)
    except Exception as exc:
        log.error("enqueue_failed", task="match_jobs", error_type=type(exc).__name__)
        return False
    return True


async def upload(db: AsyncSession, user: User, *, filename: str | None, data: bytes) -> Resume:
    settings = get_settings()
    if len(data) > settings.max_upload_mb * 1024 * 1024:
        raise InvalidUpload(f"Files can be at most {settings.max_upload_mb} MB.")
    if not data:
        raise InvalidUpload("The file is empty.")
    kind = sniff_kind(data)
    if kind is None:
        raise InvalidUpload("Only PDF and DOCX files are supported.")
    if kind == "pdf":
        try:
            pages = await asyncio.to_thread(pdf_page_count, data)
        except ExtractionError as exc:
            raise InvalidUpload(exc.message) from exc
        if pages > settings.max_resume_pages:
            raise InvalidUpload(f"Resumes can be at most {settings.max_resume_pages} pages long.")

    sha = hashlib.sha256(data).hexdigest()
    # Lock the user row so concurrent uploads get distinct version numbers.
    await db.execute(select(User.id).where(User.id == user.id).with_for_update())
    duplicate = await db.scalar(
        select(Resume.version).where(Resume.user_id == user.id, Resume.file_sha256 == sha)
    )
    if duplicate is not None:
        raise Conflict(
            f"You already uploaded this exact file (version {duplicate}). "
            "Use “Parse again” on that version instead."
        )
    next_version = (
        await db.scalar(select(func.max(Resume.version)).where(Resume.user_id == user.id)) or 0
    ) + 1

    resume_id = uuid7()
    key = f"resumes/{user.id}/{resume_id}.bin"
    encrypted = crypto.encrypt_file(data)
    await asyncio.to_thread(get_storage().put, key, encrypted)

    resume = Resume(
        id=resume_id,
        user_id=user.id,
        version=next_version,
        status=ResumeStatus.UPLOADED,
        file_key=key,
        file_name=_safe_filename(filename),
        mime_type=MIME_TYPES[kind],
        file_sha256=sha,
    )
    db.add(resume)
    await db.commit()
    await db.refresh(resume)
    _enqueue_parse(resume.id)
    await db.refresh(resume)  # inline (test) runs change it
    return resume


async def update_profile(
    db: AsyncSession, user: User, resume: Resume, profile: ResumeProfile
) -> Resume:
    if resume.status != ResumeStatus.PARSED:
        raise ResumeNotReady()
    final, derived = finalize_profile(profile)
    resume.profile = final.model_dump(mode="json")
    resume.profile_version += 1
    resume.skills_index = derived.skills_index
    resume.total_years_experience = (
        Decimal(str(derived.total_years_experience))
        if derived.total_years_experience is not None
        else None
    )
    resume.seniority = derived.seniority
    resume.embedding = None  # stale until re-embedded
    resume.embedding_model = None
    if user.onboarding_step in (OnboardingStep.RESUME, OnboardingStep.PROFILE):
        user.onboarding_step = OnboardingStep.PREFERENCES
    await db.commit()
    await db.refresh(resume)
    _enqueue_embed(resume.id, resume.profile_version)
    await db.refresh(resume)
    return resume


async def activate(db: AsyncSession, user: User, resume: Resume) -> Resume:
    if resume.status != ResumeStatus.PARSED:
        raise ResumeNotReady("Only parsed resumes can be made active.")
    await db.execute(
        update(Resume)
        .where(Resume.user_id == user.id, Resume.id != resume.id, Resume.is_active)
        .values(is_active=False)
    )
    await db.flush()
    resume.is_active = True
    await db.commit()
    await db.refresh(resume)
    if resume.embedding is not None:
        enqueue_match(user.id)  # this version's scores (cached ones are reused)
    return resume


async def reparse(db: AsyncSession, resume: Resume) -> Resume:
    if resume.status not in (ResumeStatus.FAILED, ResumeStatus.PARSED):
        raise Conflict("This resume is already being parsed.")
    resume.status = ResumeStatus.UPLOADED
    resume.error = None
    await db.commit()
    _enqueue_parse(resume.id)
    await db.refresh(resume)
    return resume


async def read_file(resume: Resume) -> bytes:
    blob = await asyncio.to_thread(get_storage().get, resume.file_key)
    return crypto.decrypt_file(blob)


async def delete(db: AsyncSession, user: User, resume: Resume) -> None:
    was_active = resume.is_active
    key = resume.file_key
    await db.delete(resume)
    await db.flush()
    if was_active:
        successor = await db.scalar(
            select(Resume)
            .where(Resume.user_id == user.id, Resume.status == ResumeStatus.PARSED)
            .order_by(Resume.version.desc())
            .limit(1)
        )
        if successor is not None:
            successor.is_active = True
    await db.commit()
    await asyncio.to_thread(get_storage().delete, key)
