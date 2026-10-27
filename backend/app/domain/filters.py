"""Stage-1 hard filters: cheap rules that hide jobs the user would never want, with a reason.

Unknown data never filters a job out (no salary, no location, no seniority -> pass).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from functools import lru_cache
from typing import Any, Protocol

import pycountry

from app.domain.dedupe import normalize_company
from app.models.enums import RemoteType, SalaryPeriod, Seniority

SENIORITY_RANK: dict[Seniority, int] = {
    Seniority.INTERN: 0,
    Seniority.JUNIOR: 1,
    Seniority.MID: 2,
    Seniority.SENIOR: 3,
    Seniority.MANAGER: 3,
    Seniority.STAFF: 4,
    Seniority.PRINCIPAL: 5,
    Seniority.DIRECTOR: 5,
}
_ANNUAL = {SalaryPeriod.YEAR: 1, SalaryPeriod.MONTH: 12, SalaryPeriod.HOUR: 2080}


class JobLike(Protocol):
    title: str
    company_name: str
    description_text: str | None
    remote_type: RemoteType
    location_raw: str | None
    seniority: Seniority | None
    min_years_experience: Decimal | None
    salary_max: int | None
    salary_currency: str | None
    salary_period: SalaryPeriod | None
    posted_at: datetime | None


@dataclass(frozen=True)
class FilterPrefs:
    exclude_companies: list[str] = field(default_factory=list)
    exclude_keywords: list[str] = field(default_factory=list)
    include_keywords: list[str] = field(default_factory=list)
    remote_types: list[str] = field(default_factory=list)
    locations: list[dict[str, Any]] = field(default_factory=list)
    salary_min: int | None = None
    salary_currency: str = "USD"
    posted_within_days: int = 30


@dataclass(frozen=True)
class CandidateLevel:
    years: float | None
    seniority: Seniority | None


def _has_word(text: str, word: str) -> bool:
    return re.search(rf"(?<!\w){re.escape(word.lower())}(?!\w)", text) is not None


@lru_cache(maxsize=256)
def country_names(code: str) -> tuple[str, ...]:
    """Lowercase names a job location might use for an ISO-2 country code."""
    country = pycountry.countries.get(alpha_2=code.upper())
    if country is None:
        return (code.lower(),)
    names = {country.name, getattr(country, "common_name", None), country.alpha_3}
    names.add(country.alpha_2)
    if code.lower() == "us":
        names |= {"USA", "United States", "U.S."}
    if code.lower() == "gb":
        names |= {"UK", "United Kingdom", "England", "Scotland", "Wales"}
    return tuple(sorted(n.lower() for n in names if n))


def location_matches(location: str, wanted: dict[str, Any]) -> bool:
    """A job location fits a preferred place: same city, or same country if no city is set."""
    text = location.lower()
    for key in ("city", "region"):
        if wanted.get(key):
            return _has_word(text, str(wanted[key]))
    country = wanted.get("country")
    return bool(country) and any(_has_word(text, n) for n in country_names(str(country)))


def _annual(amount: int, period: SalaryPeriod | None) -> int:
    return amount * _ANNUAL.get(period or SalaryPeriod.YEAR, 1)


def hard_filter_reasons(
    job: JobLike, prefs: FilterPrefs, level: CandidateLevel, now: datetime | None = None
) -> list[str]:
    now = now or datetime.now(UTC)
    reasons: list[str] = []
    text = f"{job.title}\n{job.description_text or ''}".lower()

    excluded = {normalize_company(c) for c in prefs.exclude_companies}
    if normalize_company(job.company_name) in excluded:
        reasons.append("excluded_company")
    if any(_has_word(text, k) for k in prefs.exclude_keywords):
        reasons.append("excluded_keyword")
    if prefs.include_keywords and not any(_has_word(text, k) for k in prefs.include_keywords):
        reasons.append("missing_include_keyword")

    if (
        prefs.remote_types
        and job.remote_type != RemoteType.UNKNOWN
        and job.remote_type.value not in prefs.remote_types
    ):
        reasons.append("remote_mismatch")
    elif (
        job.remote_type in (RemoteType.ONSITE, RemoteType.HYBRID)
        and prefs.locations
        and job.location_raw
        and not any(location_matches(job.location_raw, loc) for loc in prefs.locations)
    ):
        reasons.append("location_mismatch")

    gap = False
    if job.seniority and level.seniority:
        gap = SENIORITY_RANK[job.seniority] - SENIORITY_RANK[level.seniority] > 2
    if job.min_years_experience is not None and level.years is not None:
        gap = gap or float(job.min_years_experience) - level.years > 3
    if gap:
        reasons.append("seniority_gap")

    same_currency = (job.salary_currency or prefs.salary_currency) == prefs.salary_currency
    if (
        prefs.salary_min
        and job.salary_max
        and same_currency
        and _annual(job.salary_max, job.salary_period) < prefs.salary_min
    ):
        reasons.append("salary_below_floor")

    if job.posted_at and job.posted_at < now - timedelta(days=prefs.posted_within_days):
        reasons.append("stale")
    return reasons


FILTER_LABELS = {
    "excluded_company": "Company you excluded",
    "excluded_keyword": "Contains a keyword you excluded",
    "missing_include_keyword": "Missing your must-have keywords",
    "remote_mismatch": "Work arrangement you didn't select",
    "location_mismatch": "Outside your locations",
    "seniority_gap": "Far more senior than your experience",
    "salary_below_floor": "Pays below your minimum",
    "stale": "Posted too long ago",
}
