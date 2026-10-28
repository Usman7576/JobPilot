from __future__ import annotations

from typing import Annotated

from pydantic import Field, StringConstraints, field_validator

from app.models.enums import RemoteType, SearchKind, Seniority
from app.schemas.common import ApiModel

Term = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=80)]


def _dedupe(values: list[str]) -> list[str]:
    seen: dict[str, str] = {}
    for v in values:
        seen.setdefault(v.lower(), v)
    return list(seen.values())


class PreferredLocation(ApiModel):
    city: Annotated[str, StringConstraints(strip_whitespace=True, max_length=80)] | None = None
    region: Annotated[str, StringConstraints(strip_whitespace=True, max_length=80)] | None = None
    # ISO 3166-1 alpha-2, lowercase (e.g. "us", "gb", "pk")
    country: Annotated[
        str, StringConstraints(strip_whitespace=True, to_lower=True, pattern=r"^[a-z]{2}$")
    ]
    radius_km: int | None = Field(default=None, ge=0, le=500)

    @property
    def label(self) -> str:
        return ", ".join(p for p in (self.city, self.region, self.country.upper()) if p)


class PreferencesBase(ApiModel):
    target_titles: list[Term] = Field(default_factory=list, max_length=10)
    locations: list[PreferredLocation] = Field(default_factory=list, max_length=5)
    remote_types: list[RemoteType] = Field(default_factory=list)
    experience_levels: list[Seniority] = Field(default_factory=list)
    salary_min: int | None = Field(default=None, ge=0, le=10_000_000)
    salary_currency: Annotated[str, StringConstraints(to_upper=True, pattern=r"^[A-Za-z]{3}$")] = (
        "USD"
    )
    include_keywords: list[Term] = Field(default_factory=list, max_length=30)
    exclude_keywords: list[Term] = Field(default_factory=list, max_length=30)
    exclude_companies: list[Term] = Field(default_factory=list, max_length=100)
    sources: list[Term] = Field(default_factory=list, max_length=20)
    posted_within_days: int = Field(default=7, ge=1, le=30)
    results_per_source: int = Field(default=30, ge=5, le=100)
    daily_search_enabled: bool = False
    daily_search_hour: int = Field(default=8, ge=0, le=23)
    daily_search_kinds: list[SearchKind] = Field(
        default_factory=lambda: [SearchKind.JOBS], min_length=1, max_length=2
    )
    digest_enabled: bool = True
    digest_min_score: int = Field(default=80, ge=0, le=100)

    @field_validator(
        "target_titles", "include_keywords", "exclude_keywords", "exclude_companies", "sources"
    )
    @classmethod
    def _unique(cls, v: list[str]) -> list[str]:
        return _dedupe(v)

    @field_validator("remote_types")
    @classmethod
    def _no_unknown(cls, v: list[RemoteType]) -> list[RemoteType]:
        return [r for r in dict.fromkeys(v) if r != RemoteType.UNKNOWN]


class PreferencesIn(PreferencesBase):
    pass


class PreferencesOut(PreferencesBase):
    is_saved: bool  # False when these are defaults the user hasn't saved yet


class SourceOut(ApiModel):
    name: str
    label: str
    kind: str  # api | scraper
    default_on: bool
    requires_key: bool
    configured: bool
    paused_seconds: int
    note: str
