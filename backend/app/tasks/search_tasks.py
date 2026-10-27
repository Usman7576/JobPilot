from __future__ import annotations

import uuid
from datetime import UTC, datetime

from celery.exceptions import SoftTimeLimitExceeded
from sqlalchemy.orm import Session

from app.db.session import sync_session
from app.models import SearchRun
from app.models.enums import SearchStatus
from app.services import search_pipeline
from app.tasks.celery_app import celery_app


@celery_app.task(soft_time_limit=15 * 60, time_limit=20 * 60)
def run_search(run_id: str) -> str | None:
    rid = uuid.UUID(run_id)
    with sync_session() as session:
        try:
            status = search_pipeline.run_search(session, rid)
        except SoftTimeLimitExceeded:
            session.rollback()
            _fail(session, rid, "The search took too long and was stopped.")
            return SearchStatus.FAILED.value
        except Exception:
            session.rollback()
            _fail(session, rid, "The search failed unexpectedly.")
            raise
        return status.value if status else None


def _fail(session: Session, run_id: uuid.UUID, message: str) -> None:
    run = session.get(SearchRun, run_id)
    if run is not None and run.status in search_pipeline.ACTIVE_STATUSES:
        run.status = SearchStatus.FAILED
        run.error = message
        run.finished_at = datetime.now(UTC)
        session.commit()
