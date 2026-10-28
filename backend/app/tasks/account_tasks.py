from __future__ import annotations

import uuid

from app.db.session import sync_session
from app.services import account_service
from app.tasks.celery_app import celery_app


@celery_app.task(autoretry_for=(OSError,), retry_backoff=30, max_retries=5)
def purge_account(user_id: str) -> bool:
    """Delete an account that asked to be deleted: files first, then every row."""
    with sync_session() as session:
        return account_service.purge(session, uuid.UUID(user_id))


@celery_app.task
def purge_pending_accounts() -> int:
    """Hourly safety net: purges deletions whose first attempt didn't run."""
    with sync_session() as session:
        ids = account_service.pending_deletions(session)
        return sum(account_service.purge(session, i) for i in ids)
