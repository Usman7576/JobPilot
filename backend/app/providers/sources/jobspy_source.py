"""Scrapers via python-jobspy: public listings only, never logged in, opt-in per user."""

from __future__ import annotations

import math
from datetime import UTC, date, datetime
from typing import Any

from app.core.config import get_settings
from app.providers.sources.base import RawJob, SourceError, SourceInfo, SourceQuery

_NOTE = (
    "Scrapes public listings (no login). Can break or be blocked without notice, and most "
    "job boards' terms forbid scraping. You're responsible for complying with them."
)
_PERIODS = {"yearly": "year", "monthly": "month", "hourly": "hour"}


def _clean(value: Any) -> Any:
    """pandas uses NaN for missing values."""
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return None
    return value


def _location(value: Any) -> str | None:
    value = _clean(value)
    if isinstance(value, dict):
        parts = [value.get("city"), value.get("state"), value.get("country")]
        text = ", ".join(str(p) for p in parts if p and not isinstance(p, float))
        return text or None
    return str(value) if value else None


def _posted(value: Any) -> datetime | None:
    value = _clean(value)
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    if isinstance(value, date):
        return datetime(value.year, value.month, value.day, tzinfo=UTC)
    return None


class JobSpySource:
    def __init__(self, site: str, label: str, interval: float) -> None:
        self.site = site
        self.info = SourceInfo(
            name=site,
            label=label,
            kind="scraper",
            default_on=False,
            requires_key=False,
            note=_NOTE,
            min_interval_seconds=interval,
        )

    def is_configured(self) -> bool:
        return True

    def fetch(self, query: SourceQuery) -> list[RawJob]:
        from jobspy import scrape_jobs  # heavy import (pandas); only when scraping

        settings = get_settings()
        kwargs: dict[str, Any] = {
            "site_name": [self.site],
            "search_term": query.search_term,
            "location": None if query.remote_only else query.location,
            "is_remote": query.remote_only,
            # LinkedIn starts rate-limiting past ~50 results per query.
            "results_wanted": min(query.results_wanted, 50),
            "hours_old": query.posted_within_days * 24,
            "country_indeed": settings.jobspy_country_indeed,
            "description_format": "markdown",
            "fetch_description": settings.jobspy_fetch_description,
            "verbose": 0,
        }
        if query.internship:
            kwargs["search_term"] = f"{query.search_term} intern"
            kwargs["job_type"] = "internship"
            if self.site == "indeed":
                # Indeed can't combine a job type with a date filter; dates are checked later.
                kwargs.pop("hours_old")
        if self.site == "google":
            where = "remote" if query.remote_only else (query.location or "")
            what = "internships" if query.internship else "jobs"
            kwargs["google_search_term"] = f"{query.search_term} {what} {where} since last week"
        if settings.jobspy_proxies:
            kwargs["proxies"] = settings.jobspy_proxies

        try:
            frame = scrape_jobs(**kwargs)
        except Exception as exc:
            raise SourceError("scrape_failed", f"{self.info.label} couldn't be scraped.") from exc
        errors = (getattr(frame, "attrs", {}) or {}).get("errors") or {}
        if errors and frame.empty:
            raise SourceError("blocked", f"{self.info.label} blocked or failed the request.")

        out: list[RawJob] = []
        for row in frame.to_dict("records"):
            url = _clean(row.get("job_url"))
            title = _clean(row.get("title"))
            if not url or not title:
                continue
            emails = _clean(row.get("emails")) or []
            interval = _clean(row.get("interval"))
            out.append(
                RawJob(
                    source=self.info.name,
                    source_job_id=str(_clean(row.get("id")) or url),
                    url=str(url),
                    apply_url=_clean(row.get("job_url_direct")),
                    title=str(title),
                    company=str(_clean(row.get("company")) or "Unknown"),
                    company_url=_clean(row.get("company_url_direct"))
                    or _clean(row.get("company_url")),
                    location=_location(row.get("location")),
                    description=_clean(row.get("description")),
                    is_remote=_clean(row.get("is_remote")),
                    posted_at=_posted(row.get("date_posted")),
                    salary_min=_clean(row.get("min_amount")),
                    salary_max=_clean(row.get("max_amount")),
                    salary_currency=_clean(row.get("currency")),
                    salary_period=_PERIODS.get(str(interval)) if interval else None,
                    job_type=str(_clean(row.get("job_type")) or "") or None,
                    emails=[str(e) for e in emails] if isinstance(emails, list) else [],
                )
            )
        return out
