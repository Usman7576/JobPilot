from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, Timestamps, UUIDPk
from app.models.constants import EMBEDDING_DIM
from app.models.enums import (
    EmploymentType,
    NormalizationStatus,
    PayStatus,
    RemoteType,
    SalaryPeriod,
    Seniority,
    pg_enum,
)


class Job(UUIDPk, Timestamps, Base):
    """A posting, deduplicated across sources and shared by all users."""

    __tablename__ = "jobs"
    __table_args__ = (
        Index(
            "ix_jobs_embedding_hnsw",
            "embedding",
            postgresql_using="hnsw",
            postgresql_with={"m": 16, "ef_construction": 64},
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
        Index("ix_jobs_posted_at", "posted_at"),
        Index("ix_jobs_required_skills", "required_skills", postgresql_using="gin"),
        Index(
            "ix_jobs_normalized_title_trgm",
            "normalized_title",
            postgresql_using="gin",
            postgresql_ops={"normalized_title": "gin_trgm_ops"},
        ),
    )

    company_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("companies.id", ondelete="SET NULL"), index=True
    )
    company_name: Mapped[str] = mapped_column(Text)
    title: Mapped[str] = mapped_column(Text)
    normalized_title: Mapped[str] = mapped_column(Text)
    location_raw: Mapped[str | None] = mapped_column(Text)
    # {city, region, country, lat, lon}
    location: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    remote_type: Mapped[RemoteType] = mapped_column(
        pg_enum(RemoteType, "remote_type"),
        default=RemoteType.UNKNOWN,
        server_default=RemoteType.UNKNOWN.value,
    )
    employment_type: Mapped[EmploymentType] = mapped_column(
        pg_enum(EmploymentType, "employment_type"),
        default=EmploymentType.UNKNOWN,
        server_default=EmploymentType.UNKNOWN.value,
    )
    seniority: Mapped[Seniority | None] = mapped_column(pg_enum(Seniority, "seniority"))
    min_years_experience: Mapped[Decimal | None] = mapped_column(Numeric(4, 1))
    salary_min: Mapped[int | None] = mapped_column(Integer)
    salary_max: Mapped[int | None] = mapped_column(Integer)
    salary_currency: Mapped[str | None] = mapped_column(String(3))
    salary_period: Mapped[SalaryPeriod | None] = mapped_column(
        pg_enum(SalaryPeriod, "salary_period")
    )
    pay_status: Mapped[PayStatus] = mapped_column(
        pg_enum(PayStatus, "pay_status"),
        default=PayStatus.UNKNOWN,
        server_default=PayStatus.UNKNOWN.value,
    )
    required_skills: Mapped[list[str]] = mapped_column(
        ARRAY(Text), default=list, server_default="{}"
    )
    nice_to_have_skills: Mapped[list[str]] = mapped_column(
        ARRAY(Text), default=list, server_default="{}"
    )
    description_html: Mapped[str | None] = mapped_column(Text)
    description_text: Mapped[str | None] = mapped_column(Text)
    contact_emails: Mapped[list[str]] = mapped_column(
        ARRAY(Text), default=list, server_default="{}"
    )
    primary_url: Mapped[str] = mapped_column(Text)
    apply_url: Mapped[str | None] = mapped_column(Text)
    url_hash: Mapped[str] = mapped_column(Text, unique=True)
    dedupe_hash: Mapped[str] = mapped_column(Text, unique=True)
    posted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    first_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    last_seen_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    normalization_status: Mapped[NormalizationStatus] = mapped_column(
        pg_enum(NormalizationStatus, "normalization_status"),
        default=NormalizationStatus.PENDING,
        server_default=NormalizationStatus.PENDING.value,
    )
    embedding: Mapped[list[float] | None] = mapped_column(Vector(EMBEDDING_DIM))
    embedding_model: Mapped[str | None] = mapped_column(Text)


class JobSourceRecord(UUIDPk, Timestamps, Base):
    """One row per board a job was seen on."""

    __tablename__ = "job_source_records"
    __table_args__ = (UniqueConstraint("source", "source_job_id"),)

    job_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"), index=True)
    source: Mapped[str] = mapped_column(Text)
    source_job_id: Mapped[str] = mapped_column(Text)
    url: Mapped[str] = mapped_column(Text)
    raw: Mapped[dict[str, Any] | None] = mapped_column(JSONB)
    scraped_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
