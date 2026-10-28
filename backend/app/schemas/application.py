from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field, StringConstraints

from app.models.enums import (
    ApplicationChannel,
    ApplicationStatus,
    ContactSource,
    DraftKind,
    EventActor,
    Tone,
)
from app.schemas.common import ApiModel

# --- what the writing prompts return ---------------------------------------------------------


class LLMWritten(BaseModel):
    model_config = ConfigDict(extra="ignore")

    greeting: str = Field(default="", max_length=200)
    body: str = Field(min_length=20, max_length=6000)
    skills_used: list[str] = Field(default_factory=list)
    achievement_ref: str = ""
    job_detail: str = ""


class LLMTweak(BaseModel):
    model_config = ConfigDict(extra="ignore")

    bullet_id: str
    suggested: str = Field(max_length=600)
    rationale: str = Field(default="", max_length=400)
    emphasized_skills: list[str] = Field(default_factory=list)


class LLMTweaks(BaseModel):
    model_config = ConfigDict(extra="ignore")

    tweaks: list[LLMTweak]


class LLMClaim(BaseModel):
    model_config = ConfigDict(extra="ignore")

    claim: str
    supporting_quote: str = ""
    where: Literal["email", "cover_letter"] = "email"


class LLMClaims(BaseModel):
    model_config = ConfigDict(extra="ignore")

    claims: list[LLMClaim]


# --- API ----------------------------------------------------------------------------------

Instructions = Annotated[str, StringConstraints(strip_whitespace=True, max_length=500)]
WritableKind = Literal["email", "cover_letter", "resume_tweaks"]


def _default_kinds() -> list[WritableKind]:
    return ["email", "cover_letter"]


class PrepareIn(ApiModel):
    tone: Tone = Tone.FORMAL
    kinds: list[WritableKind] = Field(default_factory=_default_kinds, min_length=1)
    instructions: Instructions | None = None


class RegenerateIn(ApiModel):
    kind: WritableKind
    tone: Tone = Tone.FORMAL
    instructions: Instructions | None = None


class ToneIn(ApiModel):
    tone: Tone = Tone.FORMAL


class ApplicationPatch(ApiModel):
    subject: Annotated[str, StringConstraints(strip_whitespace=True, max_length=200)] | None = None
    email_body: Annotated[str, StringConstraints(max_length=6000)] | None = None
    cover_letter_body: Annotated[str, StringConstraints(max_length=12000)] | None = None
    contact_email: EmailStr | None = None
    clear_contact: bool = False
    notes: Annotated[str, StringConstraints(max_length=4000)] | None = None


class UseDraftIn(ApiModel):
    draft_id: uuid.UUID


class FlagOut(ApiModel):
    text: str
    reason: str
    severity: Literal["block", "warn"]
    source: str


class DraftOut(ApiModel):
    id: uuid.UUID
    kind: DraftKind
    tone: Tone
    content: dict[str, Any]
    flags: list[FlagOut]
    blocked: bool
    verified: bool
    word_count: int | None
    model: str | None
    edited_by_user: bool
    created_at: datetime


class EventOut(ApiModel):
    from_status: ApplicationStatus | None
    to_status: ApplicationStatus
    actor: EventActor
    reason: str | None
    created_at: datetime


class ApplicationOut(ApiModel):
    id: uuid.UUID
    job_id: uuid.UUID
    job_title: str
    company_name: str
    apply_url: str | None
    status: ApplicationStatus
    channel: ApplicationChannel
    tone: Tone
    contact_email: str | None
    email_source: ContactSource
    email_confidence: int | None
    email: DraftOut | None
    cover_letter: DraftOut | None
    resume_tweaks: DraftOut | None
    follow_up: DraftOut | None
    follow_up_count: int
    versions: dict[str, list[DraftOut]]  # all drafts per kind, newest first
    flags_blocked: bool  # some draft has a "block" flag
    flags_acknowledged: bool
    sent_at: datetime | None  # when it was marked applied
    scheduled_send_at: datetime | None = None  # queued: when the email goes (cancellable)
    follow_up_at: datetime | None
    last_error: str | None
    notes: str | None
    resume_id: uuid.UUID | None
    resume_file_name: str | None
    is_generating: bool
    events: list[EventOut]
    created_at: datetime
    updated_at: datetime


class ApplicationListItem(ApiModel):
    id: uuid.UUID
    job_id: uuid.UUID
    job_title: str
    company_name: str
    status: ApplicationStatus
    channel: ApplicationChannel
    contact_email: str | None
    sent_at: datetime | None
    updated_at: datetime
    match_score: int | None = None


class MarkAppliedIn(ApiModel):
    channel: Literal["site", "email"] = "site"  # email = you sent it yourself


class ApplicationRef(ApiModel):
    id: uuid.UUID
    status: ApplicationStatus


class SendIn(ApiModel):
    # Only the final preview dialog sets this: nothing is sent without a person reviewing it.
    preview_confirmed: bool = False


class SendQuotaOut(ApiModel):
    cap: int
    sent_today: int
    queued: int
    remaining: int
