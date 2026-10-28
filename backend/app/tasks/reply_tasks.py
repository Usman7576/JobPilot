from __future__ import annotations

import uuid

from app.db.session import sync_session
from app.services import reply_service
from app.tasks.celery_app import celery_app


@celery_app.task(soft_time_limit=5 * 60)
def check_replies(user_id: str) -> int:
    """Look for replies to this user's applications; returns how many cards moved."""
    with sync_session() as session:
        return reply_service.check(session, uuid.UUID(user_id)).moved


@celery_app.task
def check_all_replies() -> int:
    """Run by beat every 15 minutes for everyone with reply detection on."""
    with sync_session() as session:
        users = reply_service.users_to_check(session)
    for user_id in users:
        check_replies.delay(str(user_id))
    return len(users)
