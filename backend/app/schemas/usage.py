from __future__ import annotations

from datetime import date

from app.models.enums import UsageFeature
from app.schemas.common import ApiModel


class FeatureUsage(ApiModel):
    feature: UsageFeature
    requests: int
    input_tokens: int
    output_tokens: int
    cost_usd: float


class ModelUsage(ApiModel):
    provider: str
    model: str
    requests: int


class DayUsage(ApiModel):
    day: date
    requests: int


class UsageOut(ApiModel):
    month_start: date
    requests: int
    input_tokens: int
    output_tokens: int
    cost_usd: float  # free tiers cost 0
    by_feature: list[FeatureUsage]
    by_model: list[ModelUsage]
    daily: list[DayUsage]  # last 30 days
    # Free-tier quota is per API key, shared by everyone using this app.
    requests_left_today: int | None
    daily_request_limit: int | None
    provider: str
    writing_provider: str
