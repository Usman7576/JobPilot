from __future__ import annotations

import uuid

from app.db.session import sync_session
from app.models.enums import Tone
from app.services import application_writer
from app.tasks.celery_app import celery_app


@celery_app.task(soft_time_limit=8 * 60)
def prepare_application(
    application_id: str, kinds: list[str], tone: str, instructions: str | None = None
) -> bool:
    """Find the contact and write the requested drafts (ends in READY, with last_error)."""
    with sync_session() as session:
        return application_writer.prepare(
            session, uuid.UUID(application_id), kinds, Tone(tone), instructions
        )


@celery_app.task(soft_time_limit=4 * 60)
def verify_application(application_id: str) -> bool:
    """Run the AI fact-check again on the current email and cover letter."""
    with sync_session() as session:
        return application_writer.reverify(session, uuid.UUID(application_id))


@celery_app.task(soft_time_limit=4 * 60)
def write_follow_up(application_id: str, tone: str) -> bool:
    """A follow-up email draft for an application that hasn't had a reply."""
    with sync_session() as session:
        return application_writer.write_follow_up(session, uuid.UUID(application_id), Tone(tone))
