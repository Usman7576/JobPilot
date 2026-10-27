from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Any

from pgvector.sqlalchemy import Vector
from sqlalchemy import Boolean, ForeignKey, Index, Integer, Numeric, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, Timestamps, UUIDPk
from app.db.types import EncryptedJSON, EncryptedText
from app.models.constants import EMBEDDING_DIM
from app.models.enums import ResumeStatus, Seniority, pg_enum


class Resume(UUIDPk, Timestamps, Base):
    __tablename__ = "resumes"
    __table_args__ = (
        UniqueConstraint("user_id", "version"),
        # At most one active resume per user.
        Index(
            "uq_resumes_one_active_per_user",
            "user_id",
            unique=True,
            postgresql_where=text("is_active"),
        ),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    version: Mapped[int] = mapped_column(Integer)
    label: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    status: Mapped[ResumeStatus] = mapped_column(
        pg_enum(ResumeStatus, "resume_status"),
        default=ResumeStatus.UPLOADED,
        server_default=ResumeStatus.UPLOADED.value,
    )
    error: Mapped[str | None] = mapped_column(Text)
    file_key: Mapped[str] = mapped_column(Text)
    file_name: Mapped[str] = mapped_column(EncryptedText)
    mime_type: Mapped[str] = mapped_column(Text)
    file_sha256: Mapped[str] = mapped_column(Text)
    raw_text: Mapped[str | None] = mapped_column(EncryptedText)
    parsed: Mapped[dict[str, Any] | None] = mapped_column(EncryptedJSON)
    profile: Mapped[dict[str, Any] | None] = mapped_column(EncryptedJSON)
    profile_version: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    skills_index: Mapped[list[str]] = mapped_column(ARRAY(Text), default=list, server_default="{}")
    total_years_experience: Mapped[Decimal | None] = mapped_column(Numeric(4, 1))
    seniority: Mapped[Seniority | None] = mapped_column(pg_enum(Seniority, "seniority"))
    embedding: Mapped[list[float] | None] = mapped_column(Vector(EMBEDDING_DIM))
    embedding_model: Mapped[str | None] = mapped_column(Text)
    prompt_version: Mapped[str | None] = mapped_column(Text)
