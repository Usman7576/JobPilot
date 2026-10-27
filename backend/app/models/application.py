from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    SmallInteger,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import CITEXT, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, Timestamps, UUIDPk
from app.db.types import EncryptedJSON, EncryptedText
from app.models.enums import (
    ApplicationChannel,
    ApplicationStatus,
    ContactSource,
    DraftKind,
    EventActor,
    ReplyClassification,
    SendStatus,
    Tone,
    pg_enum,
)


class Application(UUIDPk, Timestamps, Base):
    __tablename__ = "applications"
    __table_args__ = (
        UniqueConstraint("user_id", "job_id"),
        Index("ix_applications_user_status", "user_id", "status"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    job_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"))
    resume_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("resumes.id", ondelete="SET NULL")
    )
    channel: Mapped[ApplicationChannel] = mapped_column(
        pg_enum(ApplicationChannel, "application_channel"),
        default=ApplicationChannel.NONE,
        server_default=ApplicationChannel.NONE.value,
    )
    status: Mapped[ApplicationStatus] = mapped_column(
        pg_enum(ApplicationStatus, "application_status"),
        default=ApplicationStatus.SAVED,
        server_default=ApplicationStatus.SAVED.value,
    )
    contact_email: Mapped[str | None] = mapped_column(CITEXT)
    email_source: Mapped[ContactSource] = mapped_column(
        pg_enum(ContactSource, "contact_source"),
        default=ContactSource.NONE,
        server_default=ContactSource.NONE.value,
    )
    email_confidence: Mapped[int | None] = mapped_column(SmallInteger)
    current_draft_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("application_drafts.id", ondelete="SET NULL", use_alter=True)
    )
    subject: Mapped[str | None] = mapped_column(EncryptedText)
    body: Mapped[str | None] = mapped_column(EncryptedText)
    cover_letter: Mapped[str | None] = mapped_column(EncryptedText)
    tone: Mapped[Tone] = mapped_column(
        pg_enum(Tone, "tone"), default=Tone.FORMAL, server_default=Tone.FORMAL.value
    )
    guardrail_flags_acknowledged_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True)
    )
    idempotency_key: Mapped[str | None] = mapped_column(Text, unique=True)
    queued_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    scheduled_send_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    send_task_id: Mapped[str | None] = mapped_column(Text)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    gmail_message_id: Mapped[str | None] = mapped_column(Text)
    gmail_thread_id: Mapped[str | None] = mapped_column(Text, index=True)
    last_reply_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reply_classification: Mapped[ReplyClassification | None] = mapped_column(
        pg_enum(ReplyClassification, "reply_classification")
    )
    follow_up_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    follow_up_count: Mapped[int] = mapped_column(SmallInteger, default=0, server_default="0")
    notes: Mapped[str | None] = mapped_column(EncryptedText)
    kanban_position: Mapped[float] = mapped_column(Float, default=0.0, server_default="0")
    sheet_row_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # Why the last generation or send didn't work (shown in the Prepare panel).
    last_error: Mapped[str | None] = mapped_column(Text)


class ApplicationDraft(UUIDPk, Timestamps, Base):
    """Every generation or regeneration is kept so the user can switch versions."""

    __tablename__ = "application_drafts"

    application_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("applications.id", ondelete="CASCADE"), index=True
    )
    kind: Mapped[DraftKind] = mapped_column(pg_enum(DraftKind, "draft_kind"))
    tone: Mapped[Tone] = mapped_column(pg_enum(Tone, "tone"))
    # Text for email / cover letter, JSON list for resume tweaks.
    content: Mapped[Any] = mapped_column(EncryptedJSON)
    # {claims: [{text, traced, reason, severity}], blocked: bool}
    guardrail_report: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    prompt_version: Mapped[str | None] = mapped_column(Text)
    model: Mapped[str | None] = mapped_column(Text)
    edited_by_user: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")


class ApplicationEvent(UUIDPk, Timestamps, Base):
    __tablename__ = "application_events"

    application_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("applications.id", ondelete="CASCADE"), index=True
    )
    from_status: Mapped[ApplicationStatus | None] = mapped_column(
        pg_enum(ApplicationStatus, "application_status")
    )
    to_status: Mapped[ApplicationStatus] = mapped_column(
        pg_enum(ApplicationStatus, "application_status")
    )
    actor: Mapped[EventActor] = mapped_column(pg_enum(EventActor, "event_actor"))
    reason: Mapped[str | None] = mapped_column(Text)
    metadata_: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSONB, default=dict, server_default="{}"
    )


class EmailSendLog(UUIDPk, Timestamps, Base):
    """Source of truth for the daily send cap; survives application edits."""

    __tablename__ = "email_send_log"
    __table_args__ = (Index("ix_email_send_log_user_day", "user_id", "sent_on"),)

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    application_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("applications.id", ondelete="SET NULL")
    )
    status: Mapped[SendStatus] = mapped_column(pg_enum(SendStatus, "send_status"))
    sent_on: Mapped[date] = mapped_column(Date)
