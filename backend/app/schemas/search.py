from __future__ import annotations

import uuid
from datetime import datetime

from app.models.enums import SearchStatus, SearchTrigger, SourceRunStatus
from app.schemas.common import ApiModel


class SearchRunSourceOut(ApiModel):
    source: str
    label: str
    status: SourceRunStatus
    fetched_count: int
    error_code: str | None
    error_message: str | None
    duration_ms: int | None


class SearchRunOut(ApiModel):
    id: uuid.UUID
    trigger: SearchTrigger
    status: SearchStatus
    progress: int
    stage_detail: str | None
    counts: dict[str, int]
    error: str | None
    started_at: datetime | None
    finished_at: datetime | None
    created_at: datetime
    sources: list[SearchRunSourceOut]
    is_active: bool
