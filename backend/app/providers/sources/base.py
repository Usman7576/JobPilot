"""The JobSource interface every job provider implements (APIs and scrapers alike)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal, Protocol

SourceKind = Literal["api", "scraper"]


class SourceError(Exception):
    """A source failed. `code` is shown to the user next to the source's name."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class SourceQuery:
    search_term: str  # one target title
    location: str | None  # "Berlin, Germany", "London", None for anywhere
    country: str | None  # ISO-2 lowercase when known ("us", "gb", "de")
    remote_only: bool
    posted_within_days: int
    results_wanted: int


@dataclass
class RawJob:
    source: str
    source_job_id: str
    url: str
    title: str
    company: str
    location: str | None = None
    description: str | None = None  # text or markdown; HTML is cleaned later
    description_is_html: bool = False
    apply_url: str | None = None
    company_url: str | None = None
    is_remote: bool | None = None
    posted_at: datetime | None = None
    salary_min: float | None = None
    salary_max: float | None = None
    salary_currency: str | None = None
    salary_period: str | None = None  # year | month | hour
    job_type: str | None = None
    emails: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class SourceInfo:
    name: str
    label: str
    kind: SourceKind
    default_on: bool
    requires_key: bool
    # Shown in Settings next to the toggle.
    note: str
    # Minimum seconds between requests to this provider (politeness).
    min_interval_seconds: float


class JobSource(Protocol):
    info: SourceInfo

    def is_configured(self) -> bool: ...
    def fetch(self, query: SourceQuery) -> list[RawJob]: ...
