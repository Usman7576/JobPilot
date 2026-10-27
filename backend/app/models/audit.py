from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import ForeignKey, PrimaryKeyConstraint, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, Timestamps, UUIDPk


class AuditLog(UUIDPk, Timestamps, Base):
    """Security-relevant actions (login, token reuse, sends, deletion requests)."""

    __tablename__ = "audit_log"

    user_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    action: Mapped[str] = mapped_column(Text)
    ip_hash: Mapped[str | None] = mapped_column(Text)
    metadata_: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSONB, default=dict, server_default="{}"
    )


class IdempotencyKey(Timestamps, Base):
    __tablename__ = "idempotency_keys"
    __table_args__ = (PrimaryKeyConstraint("user_id", "key"),)

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    key: Mapped[str] = mapped_column(Text)
    endpoint: Mapped[str] = mapped_column(Text)
    response_status: Mapped[int] = mapped_column()
    response_body: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
