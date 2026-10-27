"""Status history for an application (the timeline in the tracker)."""

from __future__ import annotations

from typing import Any, Protocol

from app.models import Application, ApplicationEvent
from app.models.enums import ApplicationStatus, EventActor


class _Adds(Protocol):
    def add(self, instance: Any) -> None: ...


def record_event(
    session: _Adds,
    application: Application,
    to_status: ApplicationStatus,
    actor: EventActor,
    reason: str | None = None,
    from_status: ApplicationStatus | None = None,
    **metadata: Any,
) -> None:
    """Add a timeline row. Works with sync and async sessions (add() is synchronous)."""
    session.add(
        ApplicationEvent(
            application_id=application.id,
            from_status=from_status,
            to_status=to_status,
            actor=actor,
            reason=reason,
            metadata_=metadata,
        )
    )
