from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    SmallInteger,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, Timestamps, UUIDPk
from app.models.enums import MatchStage, Recommendation, pg_enum


class UserJob(UUIDPk, Timestamps, Base):
    """A user's relation to a job, independent of resume version (dismiss, bookmark)."""

    __tablename__ = "user_jobs"
    __table_args__ = (UniqueConstraint("user_id", "job_id"),)

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    job_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"), index=True)
    first_run_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("search_runs.id", ondelete="SET NULL")
    )
    discovered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    dismissed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    bookmarked: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")
    viewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class JobMatch(UUIDPk, Timestamps, Base):
    """Score of one job against one resume profile version (the score cache key)."""

    __tablename__ = "job_matches"
    __table_args__ = (
        UniqueConstraint("job_id", "resume_id", "profile_version"),
        Index(
            "ix_job_matches_feed",
            "user_id",
            "resume_id",
            "profile_version",
            "overall_score",
        ),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    job_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"), index=True)
    resume_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("resumes.id", ondelete="CASCADE"))
    profile_version: Mapped[int] = mapped_column(Integer)
    similarity: Mapped[float | None] = mapped_column(Float)
    hard_filter_passed: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    hard_filter_reasons: Mapped[list[str]] = mapped_column(
        ARRAY(Text), default=list, server_default="{}"
    )
    stage: Mapped[MatchStage] = mapped_column(
        pg_enum(MatchStage, "match_stage"),
        default=MatchStage.STAGE1,
        server_default=MatchStage.STAGE1.value,
    )
    breakdown: Mapped[dict[str, int] | None] = mapped_column(JSONB)
    overall_score: Mapped[int | None] = mapped_column(SmallInteger)
    weights_version: Mapped[str | None] = mapped_column(Text)
    matched_skills: Mapped[list[str]] = mapped_column(
        ARRAY(Text), default=list, server_default="{}"
    )
    missing_skills: Mapped[list[str]] = mapped_column(
        ARRAY(Text), default=list, server_default="{}"
    )
    # [{code, message, severity}]
    red_flags: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, default=list, server_default="[]"
    )
    why_good_fit: Mapped[str | None] = mapped_column(Text)
    llm_recommendation: Mapped[Recommendation | None] = mapped_column(
        pg_enum(Recommendation, "recommendation")
    )
    recommendation: Mapped[Recommendation | None] = mapped_column(
        pg_enum(Recommendation, "recommendation")
    )
    failure_reason: Mapped[str | None] = mapped_column(Text)
    prompt_version: Mapped[str | None] = mapped_column(Text)
    model: Mapped[str | None] = mapped_column(Text)
    scored_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
