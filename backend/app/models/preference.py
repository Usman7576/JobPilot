from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import Boolean, ForeignKey, Integer, SmallInteger, String, Text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, Timestamps


class Preference(Timestamps, Base):
    __tablename__ = "preferences"

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    target_titles: Mapped[list[str]] = mapped_column(ARRAY(Text), default=list, server_default="{}")
    # [{city, region, country, radius_km}]
    locations: Mapped[list[dict[str, Any]]] = mapped_column(
        JSONB, default=list, server_default="[]"
    )
    # Values from RemoteType / Seniority; validated by the API schemas.
    remote_types: Mapped[list[str]] = mapped_column(ARRAY(Text), default=list, server_default="{}")
    experience_levels: Mapped[list[str]] = mapped_column(
        ARRAY(Text), default=list, server_default="{}"
    )
    salary_min: Mapped[int | None] = mapped_column(Integer)
    salary_currency: Mapped[str] = mapped_column(String(3), default="USD", server_default="USD")
    include_keywords: Mapped[list[str]] = mapped_column(
        ARRAY(Text), default=list, server_default="{}"
    )
    exclude_keywords: Mapped[list[str]] = mapped_column(
        ARRAY(Text), default=list, server_default="{}"
    )
    exclude_companies: Mapped[list[str]] = mapped_column(
        ARRAY(Text), default=list, server_default="{}"
    )
    sources: Mapped[list[str]] = mapped_column(ARRAY(Text), default=list, server_default="{}")
    posted_within_days: Mapped[int] = mapped_column(SmallInteger, default=7, server_default="7")
    results_per_source: Mapped[int] = mapped_column(SmallInteger, default=50, server_default="50")
    daily_search_enabled: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default="false"
    )
    daily_search_hour: Mapped[int] = mapped_column(SmallInteger, default=8, server_default="8")
    # "jobs" and/or "internships": what the daily search looks for.
    daily_search_kinds: Mapped[list[str]] = mapped_column(
        ARRAY(Text), default=lambda: ["jobs"], server_default="{jobs}"
    )
    digest_enabled: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    digest_min_score: Mapped[int] = mapped_column(SmallInteger, default=80, server_default="80")
    stage1_top_n: Mapped[int | None] = mapped_column(SmallInteger)
