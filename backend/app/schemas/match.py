from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import MatchStage, Recommendation
from app.schemas.common import ApiModel


class LLMRedFlag(BaseModel):
    code: str = Field(max_length=60)
    message: str = Field(max_length=300)
    severity: Literal["low", "medium", "high"] = "medium"


class LLMJobScore(BaseModel):
    model_config = ConfigDict(extra="ignore")

    job_ref: str
    skills_match: float
    experience_match: float
    seniority_fit: float
    domain_relevance: float
    matched_skills: list[str] = Field(default_factory=list)
    missing_skills: list[str] = Field(default_factory=list)
    red_flags: list[LLMRedFlag] = Field(default_factory=list)
    why_good_fit: str = Field(default="", max_length=800)
    apply_recommendation: Recommendation | None = None


class LLMScoreBatch(BaseModel):
    model_config = ConfigDict(extra="ignore")

    results: list[LLMJobScore]


class RedFlagOut(ApiModel):
    code: str
    message: str
    severity: Literal["low", "medium", "high"]


class MatchSummary(ApiModel):
    """What a job card shows about the match."""

    stage: MatchStage
    overall_score: int | None
    recommendation: Recommendation | None
    similarity: float | None
    hard_filter_passed: bool
    hard_filter_reasons: list[str]


class MatchDetail(MatchSummary):
    breakdown: dict[str, int] | None
    matched_skills: list[str]
    missing_skills: list[str]
    red_flags: list[RedFlagOut]
    why_good_fit: str | None
    failure_reason: str | None
    scored_at: datetime | None


class ScoreEstimate(ApiModel):
    """How many AI requests scoring the user's unscored jobs would take right now."""

    jobs_to_score: int
    llm_requests: int
    requests_left_today: int | None
    has_resume: bool
