"""Search APIs that need a free key: Adzuna, Jooble, SerpAPI (Google Jobs)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from app.core.config import get_settings
from app.providers.sources.base import RawJob, SourceInfo, SourceQuery
from app.providers.sources.feeds import _parse_iso
from app.providers.sources.http import request_json

ADZUNA_COUNTRIES = {
    "at", "au", "be", "br", "ca", "ch", "de", "es", "fr", "gb", "in", "it", "mx", "nl",
    "nz", "pl", "sg", "us", "za",
}  # fmt: skip


def _city(location: str | None) -> str | None:
    if not location:
        return None
    return location.split(",")[0].strip() or None


class AdzunaSource:
    info = SourceInfo(
        name="adzuna",
        label="Adzuna",
        kind="api",
        default_on=True,
        requires_key=True,
        note="Free developer API with salary data in 19 countries. Needs ADZUNA_APP_ID/KEY.",
        min_interval_seconds=1,
    )

    def is_configured(self) -> bool:
        s = get_settings()
        return bool(s.adzuna_app_id and s.adzuna_app_key)

    def fetch(self, query: SourceQuery) -> list[RawJob]:
        s = get_settings()
        country = query.country if query.country in ADZUNA_COUNTRIES else s.adzuna_default_country
        params: dict[str, Any] = {
            "app_id": s.adzuna_app_id,
            "app_key": s.adzuna_app_key,
            "what": query.search_term + (" remote" if query.remote_only else ""),
            "results_per_page": min(query.results_wanted, 50),
            "max_days_old": query.posted_within_days,
            "sort_by": "date",
            "content-type": "application/json",
        }
        if (city := _city(query.location)) and not query.remote_only:
            params["where"] = city
        url = f"https://api.adzuna.com/v1/api/jobs/{country}/search/1"
        data = request_json("GET", url, params=params)
        out: list[RawJob] = []
        for item in data.get("results") or []:
            out.append(
                RawJob(
                    source=self.info.name,
                    source_job_id=str(item["id"]),
                    url=str(item["redirect_url"]),
                    title=str(item.get("title") or ""),
                    company=str((item.get("company") or {}).get("display_name") or "Unknown"),
                    location=(item.get("location") or {}).get("display_name"),
                    description=item.get("description"),  # Adzuna gives a snippet only
                    description_is_html=True,
                    posted_at=_parse_iso(item.get("created")),
                    salary_min=item.get("salary_min"),
                    salary_max=item.get("salary_max"),
                    salary_currency=None,
                    salary_period="year" if item.get("salary_min") else None,
                    job_type=item.get("contract_time"),
                )
            )
        return out


class JoobleSource:
    info = SourceInfo(
        name="jooble",
        label="Jooble",
        kind="api",
        default_on=True,
        requires_key=True,
        note="Free aggregator API covering many job boards. Needs JOOBLE_API_KEY.",
        min_interval_seconds=1,
    )

    def is_configured(self) -> bool:
        return bool(get_settings().jooble_api_key)

    def fetch(self, query: SourceQuery) -> list[RawJob]:
        body: dict[str, Any] = {
            "keywords": query.search_term + (" remote" if query.remote_only else ""),
            "page": 1,
            "ResultOnPage": min(query.results_wanted, 50),
            "datecreatedfrom": (
                datetime.now(UTC) - timedelta(days=query.posted_within_days)
            ).strftime("%Y-%m-%d"),
        }
        if query.location and not query.remote_only:
            body["location"] = query.location
        data = request_json(
            "POST", f"https://jooble.org/api/{get_settings().jooble_api_key}", json=body
        )
        out: list[RawJob] = []
        for item in data.get("jobs") or []:
            link = item.get("link")
            if not link:
                continue
            out.append(
                RawJob(
                    source=self.info.name,
                    source_job_id=str(item.get("id") or link),
                    url=str(link),
                    title=str(item.get("title") or ""),
                    company=str(item.get("company") or "Unknown"),
                    location=item.get("location"),
                    description=item.get("snippet"),
                    description_is_html=True,
                    posted_at=_parse_iso(item.get("updated")),
                    job_type=item.get("type"),
                    tags=[str(item["source"])] if item.get("source") else [],
                )
            )
        return out


class SerpApiSource:
    info = SourceInfo(
        name="serpapi",
        label="Google Jobs (SerpAPI)",
        kind="api",
        default_on=False,
        requires_key=True,
        note="Google Jobs results via SerpAPI. Small free monthly quota. Needs SERPAPI_KEY.",
        min_interval_seconds=2,
    )

    def is_configured(self) -> bool:
        return bool(get_settings().serpapi_key)

    def fetch(self, query: SourceQuery) -> list[RawJob]:
        params: dict[str, Any] = {
            "engine": "google_jobs",
            "q": query.search_term + (" remote" if query.remote_only else ""),
            "api_key": get_settings().serpapi_key,
        }
        if query.location and not query.remote_only:
            params["location"] = query.location
        data = request_json("GET", "https://serpapi.com/search.json", params=params)
        out: list[RawJob] = []
        for item in data.get("jobs_results") or []:
            apply = [o.get("link") for o in item.get("apply_options") or [] if o.get("link")]
            url = item.get("share_link") or (apply[0] if apply else None)
            if not url:
                continue
            ext = item.get("detected_extensions") or {}
            out.append(
                RawJob(
                    source=self.info.name,
                    source_job_id=str(item.get("job_id") or url),
                    url=str(url),
                    apply_url=apply[0] if apply else None,
                    title=str(item.get("title") or ""),
                    company=str(item.get("company_name") or "Unknown"),
                    location=item.get("location"),
                    description=item.get("description"),
                    is_remote=bool(ext.get("work_from_home")) or None,
                    job_type=ext.get("schedule_type"),
                )
            )
            if len(out) >= query.results_wanted:
                break
        return out
