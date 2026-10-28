from __future__ import annotations

import uuid

from app.db.session import sync_session
from app.services import sheets_service
from app.tasks.celery_app import celery_app


@celery_app.task(autoretry_for=(OSError,), retry_backoff=60, max_retries=3)
def sync_sheet(user_id: str) -> bool:
    """Rewrite the user's tracker spreadsheet (no-op when Sheets isn't connected)."""
    with sync_session() as session:
        return sheets_service.sync(session, uuid.UUID(user_id))
