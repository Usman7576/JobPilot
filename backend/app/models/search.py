from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Integer, SmallInteger, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, Timestamps, UUIDPk
from app.models.enums import SearchStatus, SearchTrigger, SourceRunStatus, pg_enum


class SearchRun(UUIDPk, Timestamps, Base):
    __tablename__ = "search_runs"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    trigger: Mapped[SearchTrigger] = mapped_column(pg_enum(SearchTrigger, "search_trigger"))
    status: Mapped[SearchStatus] = mapped_column(
        pg_enum(SearchStatus, "search_status"),
        default=SearchStatus.QUEUED,
        server_default=SearchStatus.QUEUED.value,
    )
    progress: Mapped[int] = mapped_column(SmallInteger, default=0, server_default="0")
    stage_detail: Mapped[str | None] = mapped_column(Text)
    query_snapshot: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    # {scraped, new, duplicates, filtered_out, stage1_kept, scored, strong}
    counts: Mapped[dict[str, int]] = mapped_column(JSONB, default=dict, server_default="{}")
    error: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    celery_root_id: Mapped[str | None] = mapped_column(Text)


class SearchRunSource(UUIDPk, Timestamps, Base):
    __tablename__ = "search_run_sources"

    run_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("search_runs.id", ondelete="CASCADE"), index=True
    )
    source: Mapped[str] = mapped_column(Text)
    status: Mapped[SourceRunStatus] = mapped_column(
        pg_enum(SourceRunStatus, "source_run_status"),
        default=SourceRunStatus.PENDING,
        server_default=SourceRunStatus.PENDING.value,
    )
    fetched_count: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    error_code: Mapped[str | None] = mapped_column(Text)
    error_message: Mapped[str | None] = mapped_column(Text)
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    attempts: Mapped[int] = mapped_column(SmallInteger, default=0, server_default="0")
