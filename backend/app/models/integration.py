from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, Timestamps, UUIDPk
from app.db.types import EncryptedText
from app.models.enums import IntegrationProvider, IntegrationStatus, pg_enum


class Integration(UUIDPk, Timestamps, Base):
    __tablename__ = "integrations"
    __table_args__ = (UniqueConstraint("user_id", "provider"),)

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    provider: Mapped[IntegrationProvider] = mapped_column(
        pg_enum(IntegrationProvider, "integration_provider")
    )
    status: Mapped[IntegrationStatus] = mapped_column(
        pg_enum(IntegrationStatus, "integration_status"),
        default=IntegrationStatus.DISCONNECTED,
        server_default=IntegrationStatus.DISCONNECTED.value,
    )
    google_email: Mapped[str | None] = mapped_column(Text)
    scopes: Mapped[list[str]] = mapped_column(ARRAY(Text), default=list, server_default="{}")
    access_token: Mapped[str | None] = mapped_column(EncryptedText)
    refresh_token: Mapped[str | None] = mapped_column(EncryptedText)
    token_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    # gmail: {history_id}; sheets: {spreadsheet_id, spreadsheet_url}
    config: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict, server_default="{}")
    last_sync_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(Text)
