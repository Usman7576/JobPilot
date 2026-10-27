"""Worker-side resume processing: decrypt -> extract text -> LLM parse -> finalize -> embed."""

from __future__ import annotations

import uuid
from decimal import Decimal

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core import crypto
from app.core.config import get_settings
from app.core.logging import get_logger
from app.domain.profile import embedding_text, finalize_profile
from app.domain.text_extraction import ExtractionError, extract_text, sniff_kind
from app.models import Resume, User
from app.models.enums import OnboardingStep, ResumeStatus, UsageFeature
from app.prompts.registry import load_prompt, render
from app.providers.embeddings import get_embeddings
from app.providers.llm import LLMError, LLMNotConfigured, LLMQuotaExhausted
from app.providers.storage import get_storage
from app.schemas.profile import ResumeProfile
from app.services import llm_gateway

log = get_logger(__name__)
PARSE_PROMPT = ("resume_parse", 1)

# User-facing messages for failures; never include resume content.
_LLM_MESSAGES = {
    "llm_not_configured": "AI parsing isn't set up yet: add GEMINI_API_KEY to .env and restart.",
    "llm_quota_exhausted": "The free AI quota for today is used up. Try again tomorrow.",
    "llm_rate_limited": "The AI is busy right now. Try again in a minute.",
    "llm_invalid_output": "The AI returned an unusable answer. Try parsing again.",
    "llm_error": "The AI service is unavailable right now. Try again shortly.",
}


def mark_failed(session: Session, resume_id: uuid.UUID, code: str, message: str) -> None:
    resume = session.get(Resume, resume_id)
    if resume is not None:
        _fail(session, resume, code, message)


def _fail(session: Session, resume: Resume, code: str, message: str) -> None:
    resume.status = ResumeStatus.FAILED
    resume.error = f"{code}: {message}"
    session.commit()
    log.info("resume_parse_failed", resume_id=str(resume.id), error_code=code)


def parse_resume(session: Session, resume_id: uuid.UUID) -> bool:
    """Returns True when parsed. Raises LLMRateLimited so the task can retry later."""
    resume = session.get(Resume, resume_id)
    if resume is None or resume.status not in (ResumeStatus.UPLOADED, ResumeStatus.FAILED):
        return False
    resume.status = ResumeStatus.PARSING
    resume.error = None
    session.commit()

    settings = get_settings()
    try:
        data = crypto.decrypt_file(get_storage().get(resume.file_key))
        kind = sniff_kind(data)
        if kind is None:
            raise ExtractionError("unsupported_type", "Only PDF and DOCX files are supported.")
        extracted = extract_text(data, kind, settings.max_resume_pages)
    except ExtractionError as exc:
        _fail(session, resume, exc.code, exc.message)
        return False
    resume.raw_text = extracted.text

    spec = load_prompt(*PARSE_PROMPT)
    try:
        parsed, _ = llm_gateway.generate(
            session,
            user_id=resume.user_id,
            feature=UsageFeature.RESUME_PARSE,
            prompt=render(spec, resume_text=extracted.text),
            parse=ResumeProfile.model_validate,
            ref_type="resume",
            ref_id=resume.id,
        )
    except (LLMNotConfigured, LLMQuotaExhausted) as exc:
        _fail(session, resume, exc.code, _LLM_MESSAGES[exc.code])
        return False
    except LLMError as exc:
        if exc.code == "llm_rate_limited":
            resume.status = ResumeStatus.UPLOADED  # the task retries shortly
            resume.error = None
            session.commit()
            raise
        _fail(session, resume, exc.code, _LLM_MESSAGES.get(exc.code, _LLM_MESSAGES["llm_error"]))
        return False

    profile, derived = finalize_profile(parsed)
    profile_json = profile.model_dump(mode="json")
    resume.parsed = profile_json
    resume.profile = profile_json
    resume.skills_index = derived.skills_index
    resume.total_years_experience = (
        Decimal(str(derived.total_years_experience))
        if derived.total_years_experience is not None
        else None
    )
    resume.seniority = derived.seniority
    resume.prompt_version = spec.ref
    resume.status = ResumeStatus.PARSED

    _make_active(session, resume)
    user = session.get(User, resume.user_id)
    if user is not None and user.onboarding_step == OnboardingStep.RESUME:
        user.onboarding_step = OnboardingStep.PROFILE
    session.commit()
    log.info("resume_parsed", resume_id=str(resume.id), skills=len(derived.skills_index))
    return True


def _make_active(session: Session, resume: Resume) -> None:
    session.execute(
        update(Resume)
        .where(Resume.user_id == resume.user_id, Resume.id != resume.id, Resume.is_active)
        .values(is_active=False)
    )
    session.flush()
    resume.is_active = True


def embed_resume(session: Session, resume_id: uuid.UUID, profile_version: int) -> bool:
    resume = session.get(Resume, resume_id)
    if resume is None or resume.profile is None or resume.profile_version != profile_version:
        return False  # an edit superseded this job; the newer job will embed
    provider = get_embeddings()
    text = embedding_text(ResumeProfile.model_validate(resume.profile))
    vector = provider.embed_documents([text])[0]
    # Re-check under a row lock in case the profile changed while embedding.
    locked = session.scalar(select(Resume).where(Resume.id == resume_id).with_for_update())
    if locked is None or locked.profile_version != profile_version:
        session.rollback()
        return False
    locked.embedding = vector
    locked.embedding_model = provider.model_name
    session.commit()
    return True
