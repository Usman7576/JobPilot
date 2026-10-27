from __future__ import annotations

import uuid

from app.db.session import sync_session
from app.services import matching
from app.tasks.celery_app import celery_app


@celery_app.task(soft_time_limit=10 * 60)
def match_jobs(user_id: str, job_ids: list[str] | None = None) -> int:
    """Match the user's jobs against their active resume version (or rescore `job_ids`)."""
    with sync_session() as session:
        stats = matching.match_for_user(
            session,
            uuid.UUID(user_id),
            job_ids=[uuid.UUID(j) for j in job_ids] if job_ids else None,
        )
        return stats.scored
