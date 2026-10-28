from __future__ import annotations

import uuid

from app.db.session import sync_session
from app.services import send_service
from app.tasks.celery_app import celery_app


@celery_app.task(bind=True, soft_time_limit=90)
def send_application_email(self, application_id: str, attempt: int = 1) -> str:  # type: ignore[no-untyped-def]
    """The only code path that sends an application email. It refuses anything that isn't
    QUEUED, a status only POST /applications/{id}/send sets (after the user's preview)."""
    with sync_session() as session:
        result = send_service.deliver(session, uuid.UUID(application_id), attempt)
    if result == "retry":
        self.apply_async(
            (application_id, attempt + 1),
            task_id=self.request.id,
            countdown=send_service.RETRY_SECONDS,
        )
    return result
