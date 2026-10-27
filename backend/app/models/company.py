from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, SmallInteger, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import CITEXT
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, Timestamps, UUIDPk
from app.models.enums import ContactSource, pg_enum


class Company(UUIDPk, Timestamps, Base):
    __tablename__ = "companies"

    name: Mapped[str] = mapped_column(Text)
    normalized_name: Mapped[str] = mapped_column(Text, unique=True)
    domain: Mapped[str | None] = mapped_column(Text, index=True)
    logo_url: Mapped[str | None] = mapped_column(Text)
    linkedin_url: Mapped[str | None] = mapped_column(Text)
    size_range: Mapped[str | None] = mapped_column(Text)
    industry: Mapped[str | None] = mapped_column(Text)
    description: Mapped[str | None] = mapped_column(Text)


class CompanyContact(UUIDPk, Timestamps, Base):
    """Shared cache of discovered contact emails (regex or Hunter)."""

    __tablename__ = "company_contacts"
    __table_args__ = (UniqueConstraint("company_id", "email"),)

    company_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), index=True
    )
    email: Mapped[str] = mapped_column(CITEXT)
    source: Mapped[ContactSource] = mapped_column(pg_enum(ContactSource, "contact_source"))
    confidence: Mapped[int | None] = mapped_column(SmallInteger)
    role: Mapped[str | None] = mapped_column(Text)
    verified_status: Mapped[str | None] = mapped_column(Text)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
