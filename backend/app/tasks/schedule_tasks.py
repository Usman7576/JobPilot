from __future__ import annotations

from app.db.session import sync_session
from app.services import schedule_service
from app.tasks.celery_app import celery_app


@celery_app.task
def dispatch_daily_searches() -> int:
    """Run by beat every 10 minutes: starts the daily searches that are due."""
    with sync_session() as session:
        return len(schedule_service.dispatch_due(session))
