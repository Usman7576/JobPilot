from __future__ import annotations

import uuid
from typing import Any

from app.db.session import sync_session
from app.models import Resume
from app.providers.llm import LLMRateLimited
from app.services import resume_pipeline
from app.tasks.celery_app import celery_app

MAX_RATE_LIMIT_RETRIES = 5


@celery_app.task(bind=True, max_retries=MAX_RATE_LIMIT_RETRIES)
def parse_resume(self: Any, resume_id: str) -> bool:
    rid = uuid.UUID(resume_id)
    with sync_session() as session:
        try:
            parsed = resume_pipeline.parse_resume(session, rid)
        except LLMRateLimited as exc:
            if self.request.retries >= MAX_RATE_LIMIT_RETRIES:
                resume_pipeline.mark_failed(
                    session, rid, "llm_rate_limited", "The AI is busy. Try parsing again later."
                )
                return False
            raise self.retry(exc=exc, countdown=60 * (self.request.retries + 1)) from exc
        if parsed:
            resume = session.get(Resume, rid)
            if resume is not None:
                embed_resume.delay(resume_id, resume.profile_version)
        return parsed


@celery_app.task(autoretry_for=(OSError,), retry_backoff=30, max_retries=3)
def embed_resume(resume_id: str, profile_version: int) -> bool:
    with sync_session() as session:
        embedded = resume_pipeline.embed_resume(session, uuid.UUID(resume_id), profile_version)
        resume = session.get(Resume, uuid.UUID(resume_id)) if embedded else None
        if resume is not None and resume.is_active:
            # A new profile version gets its own scores; older versions keep theirs.
            from app.tasks.matching_tasks import match_jobs

            match_jobs.delay(str(resume.user_id))
        return embedded
