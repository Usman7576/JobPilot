"""Free public job feeds without search: fetch the shared feed, filter locally.

- Arbeitnow: free, no key. Terms: don't abuse, link back. Mostly Europe + remote.
- Remotive: free, no key, remote only. Terms: max ~4 calls/day, credit Remotive, and do
  not show their jobs behind a sign-up wall, so it's opt-in and off by default.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta
from typing import Any

from app.providers.sources.base import RawJob, SourceInfo, SourceQuery
from app.providers.sources.http import cached_json, request_json

_STOP = {"and", "the", "for", "with", "of", "in", "a", "an", "to", "m/w/d", "f/m/d", "(m/w/d)"}


def term_tokens(term: str) -> list[str]:
    return [t for t in re.findall(r"[a-z0-9+#.]+", term.lower()) if len(t) > 1 and t not in _STOP]


def title_matches(term: str, title: str, tags: list[str] | None = None) -> bool:
    """Every meaningful word of the search term appears in the title or tags."""
    haystack = (title + " " + " ".join(tags or [])).lower()
    tokens = term_tokens(term)
    return bool(tokens) and all(tok in haystack for tok in tokens)


def _recent(posted: datetime | None, days: int) -> bool:
    return posted is None or posted >= datetime.now(UTC) - timedelta(days=days)


class ArbeitnowSource:
    info = SourceInfo(
        name="arbeitnow",
        label="Arbeitnow",
        kind="api",
        default_on=True,
        requires_key=False,
        note="Free public job API (mostly Europe and remote). Jobs link back to Arbeitnow.",
        min_interval_seconds=2,
    )
    URL = "https://www.arbeitnow.com/api/job-board-api"
    PAGES = 3  # 300 newest jobs per page; the feed is refreshed hourly

    def is_configured(self) -> bool:
        return True

    def _feed(self) -> list[dict[str, Any]]:
        def load() -> list[dict[str, Any]]:
            jobs: list[dict[str, Any]] = []
            for page in range(1, self.PAGES + 1):
                data = request_json("GET", self.URL, params={"page": page})
                jobs.extend(data.get("data") or [])
                if not (data.get("links") or {}).get("next"):
                    break
            return jobs

        result: list[dict[str, Any]] = cached_json("arbeitnow:feed", 3600, load)
        return result

    def fetch(self, query: SourceQuery) -> list[RawJob]:
        out: list[RawJob] = []
        city = (query.location or "").split(",")[0].strip().lower()
        for item in self._feed():
            title = str(item.get("title") or "")
            tags = [str(t) for t in item.get("tags") or []]
            remote = bool(item.get("remote"))
            location = str(item.get("location") or "")
            if not title_matches(query.search_term, title, tags):
                continue
            if query.remote_only and not remote:
                continue
            if city and not remote and city not in location.lower():
                continue
            created = item.get("created_at")
            posted = datetime.fromtimestamp(int(created), UTC) if created else None
            if not _recent(posted, query.posted_within_days):
                continue
            out.append(
                RawJob(
                    source=self.info.name,
                    source_job_id=str(item.get("slug") or item.get("url")),
                    url=str(item["url"]),
                    title=title,
                    company=str(item.get("company_name") or "Unknown"),
                    location=location or None,
                    description=item.get("description"),
                    description_is_html=True,
                    is_remote=remote,
                    posted_at=posted,
                    job_type=", ".join(item.get("job_types") or []) or None,
                    tags=tags,
                )
            )
            if len(out) >= query.results_wanted:
                break
        return out


class RemotiveSource:
    info = SourceInfo(
        name="remotive",
        label="Remotive",
        kind="api",
        default_on=False,
        requires_key=False,
        note=(
            "Remote jobs only, delayed 24h. Remotive's terms forbid showing their jobs behind "
            "a sign-up and allow only a few requests per day; enable for personal use only."
        ),
        min_interval_seconds=5,
    )
    URL = "https://remotive.com/api/remote-jobs"

    def is_configured(self) -> bool:
        return True

    def fetch(self, query: SourceQuery) -> list[RawJob]:
        term = query.search_term.strip().lower()
        # Shared across users and cached 6 hours: Remotive asks for <= 4 calls a day.
        data = cached_json(
            f"remotive:{term}",
            6 * 3600,
            lambda: request_json("GET", self.URL, params={"search": term, "limit": 100}),
        )
        out: list[RawJob] = []
        for item in data.get("jobs") or []:
            posted = _parse_iso(item.get("publication_date"))
            if not _recent(posted, query.posted_within_days):
                continue
            out.append(
                RawJob(
                    source=self.info.name,
                    source_job_id=str(item["id"]),
                    url=str(item["url"]),
                    title=str(item.get("title") or ""),
                    company=str(item.get("company_name") or "Unknown"),
                    location=item.get("candidate_required_location") or "Remote",
                    description=item.get("description"),
                    description_is_html=True,
                    is_remote=True,
                    posted_at=posted,
                    job_type=item.get("job_type"),
                    tags=[str(t) for t in item.get("tags") or []],
                    salary_min=None,
                    salary_max=None,
                )
            )
            if len(out) >= query.results_wanted:
                break
        return out


def _parse_iso(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=UTC)
