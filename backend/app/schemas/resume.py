from __future__ import annotations

import uuid
from datetime import datetime

from app.models.enums import ResumeStatus, Seniority
from app.schemas.common import ApiModel
from app.schemas.profile import ResumeProfile


class ResumeSummary(ApiModel):
    id: uuid.UUID
    version: int
    label: str | None
    is_active: bool
    status: ResumeStatus
    error_code: str | None
    error_message: str | None
    file_name: str
    mime_type: str
    profile_version: int
    total_years_experience: float | None
    seniority: Seniority | None
    skills_count: int
    has_embedding: bool
    created_at: datetime


class ResumeOut(ResumeSummary):
    profile: ResumeProfile | None


class ResumeLabelIn(ApiModel):
    label: str | None = None
