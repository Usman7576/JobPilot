from __future__ import annotations

import uuid
from datetime import date, datetime

from pydantic import Field

from app.domain.board import Column
from app.models.enums import (
    ApplicationChannel,
    ApplicationStatus,
    NotificationKind,
    ReplyClassification,
)
from app.schemas.common import ApiModel


class BoardCard(ApiModel):
    id: uuid.UUID
    job_id: uuid.UUID
    job_title: str
    company_name: str
    status: ApplicationStatus
    column: Column
    position: float
    channel: ApplicationChannel
    contact_email: str | None
    match_score: int | None
    sent_at: datetime | None
    last_reply_at: datetime | None
    reply_classification: ReplyClassification | None
    follow_up_at: datetime | None
    follow_up_due: bool
    follow_up_count: int
    updated_at: datetime


class MoveIn(ApiModel):
    column: Column
    # Neighbours after the drop, for fractional ordering (None at either end).
    before_id: uuid.UUID | None = None
    after_id: uuid.UUID | None = None
    withdrawn: bool = False  # in the Rejected column: "I withdrew" rather than "they declined"


class NotificationOut(ApiModel):
    id: uuid.UUID
    kind: NotificationKind
    title: str
    body: str | None
    link: str | None
    read: bool
    created_at: datetime


class NotificationsOut(ApiModel):
    items: list[NotificationOut]
    unread: int


class MarkReadIn(ApiModel):
    ids: list[uuid.UUID] | None = Field(default=None, max_length=200)  # None = all


class StatCards(ApiModel):
    jobs_found: int
    avg_match_score: float | None
    applied: int
    replied: int
    reply_rate: float | None  # replied / applied, None until something was applied
    interviews: int
    offers: int


class FunnelStep(ApiModel):
    step: str
    count: int


class SkillGap(ApiModel):
    skill: str
    jobs: int  # how many of your good matches ask for it


class WeekPoint(ApiModel):
    week_start: date
    applied: int
    replied: int
    interviews: int


class DashboardOut(ApiModel):
    days: int
    stats: StatCards
    funnel: list[FunnelStep]
    missing_skills: list[SkillGap]
    weekly: list[WeekPoint]
