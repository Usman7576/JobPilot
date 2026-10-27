from __future__ import annotations

import json
import time
from collections.abc import Iterator
from typing import Any

import httpx
import pandas as pd
import pytest
import respx

from app.core.config import get_settings
from app.providers.sources import SourceError, SourceQuery
from app.providers.sources.feeds import ArbeitnowSource, RemotiveSource, title_matches
from app.providers.sources.http import _redis
from app.providers.sources.jobspy_source import JobSpySource
from app.providers.sources.keyed_apis import AdzunaSource, JoobleSource, SerpApiSource
from app.services import source_guard

NOW = int(time.time())


def query(**kw: Any) -> SourceQuery:
    base: dict[str, Any] = {
        "search_term": "python developer",
        "location": "Berlin, DE",
        "country": "de",
        "remote_only": False,
        "posted_within_days": 7,
        "results_wanted": 10,
    }
    return SourceQuery(**{**base, **kw})


@pytest.fixture(autouse=True)
def clear_source_keys() -> Iterator[None]:
    def wipe() -> None:
        r = _redis()
        for pattern in ("source-cache:*", "source:*"):
            keys = r.keys(pattern)
            if keys:
                r.delete(*keys)

    wipe()
    yield
    wipe()


def test_title_matching() -> None:
    assert title_matches("python developer", "Senior Python Developer (m/w/d)")
    assert title_matches("data engineer", "Engineer, Data Platform")
    assert not title_matches("python developer", "Java Developer")
    assert title_matches("ml engineer", "Engineer", ["ML", "PyTorch"])


@respx.mock
def test_arbeitnow_filters_locally_and_caches_the_feed() -> None:
    feed = {
        "data": [
            {"slug": "a", "title": "Python Developer", "company_name": "A", "url": "https://a",
             "location": "Berlin", "remote": False, "tags": [], "created_at": NOW},
            {"slug": "b", "title": "Python Developer", "company_name": "B", "url": "https://b",
             "location": "Hamburg", "remote": False, "tags": [], "created_at": NOW},
            {"slug": "c", "title": "Senior Python Developer", "company_name": "C", "url": "https://c",
             "location": "Anywhere", "remote": True, "tags": [], "created_at": NOW},
            {"slug": "d", "title": "Java Developer", "company_name": "D", "url": "https://d",
             "location": "Berlin", "remote": False, "tags": [], "created_at": NOW},
            {"slug": "e", "title": "Python Developer", "company_name": "E", "url": "https://e",
             "location": "Berlin", "remote": False, "tags": [], "created_at": NOW - 30 * 86400},
        ],
        "links": {"next": None},
    }  # fmt: skip
    route = respx.get(ArbeitnowSource.URL).mock(return_value=httpx.Response(200, json=feed))
    src = ArbeitnowSource()
    berlin = src.fetch(query())
    assert [j.company for j in berlin] == ["A", "C"]  # Berlin + remote; old/Java/Hamburg dropped
    remote = src.fetch(query(remote_only=True))
    assert [j.company for j in remote] == ["C"]
    assert route.call_count == 1  # second fetch served from the shared cache
    assert berlin[0].description_is_html and berlin[0].posted_at is not None


@respx.mock
def test_remotive_is_opt_in_and_cached_for_hours() -> None:
    assert RemotiveSource.info.default_on is False
    route = respx.get(RemotiveSource.URL).mock(
        return_value=httpx.Response(
            200,
            json={"jobs": [{"id": 7, "url": "https://r/7", "title": "Python Dev",
                            "company_name": "R", "publication_date": "2099-01-01T00:00:00",
                            "candidate_required_location": "Worldwide", "tags": ["python"]}]},
        )
    )  # fmt: skip
    src = RemotiveSource()
    assert src.fetch(query())[0].is_remote is True
    src.fetch(query())
    assert route.call_count == 1


@respx.mock
def test_adzuna_maps_results_and_needs_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    src = AdzunaSource()
    assert not src.is_configured()
    monkeypatch.setattr(get_settings(), "adzuna_app_id", "id")
    monkeypatch.setattr(get_settings(), "adzuna_app_key", "key")
    assert src.is_configured()
    route = respx.get("https://api.adzuna.com/v1/api/jobs/de/search/1").mock(
        return_value=httpx.Response(
            200,
            json={"results": [{
                "id": "9", "redirect_url": "https://adz/9", "title": "Python Developer",
                "company": {"display_name": "Acme"}, "location": {"display_name": "Berlin"},
                "description": "Snippet", "created": "2026-10-20T10:00:00Z",
                "salary_min": 60000, "salary_max": 80000, "contract_time": "full_time",
            }]},
        )
    )  # fmt: skip
    jobs = src.fetch(query())
    params = route.calls[0].request.url.params
    assert params["what"] == "python developer" and params["where"] == "Berlin"
    assert params["max_days_old"] == "7"
    assert jobs[0].company == "Acme" and jobs[0].salary_max == 80000
    assert jobs[0].salary_period == "year"


@respx.mock
def test_adzuna_falls_back_to_default_country(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(get_settings(), "adzuna_app_id", "id")
    monkeypatch.setattr(get_settings(), "adzuna_app_key", "key")
    route = respx.get("https://api.adzuna.com/v1/api/jobs/us/search/1").mock(
        return_value=httpx.Response(200, json={"results": []})
    )
    AdzunaSource().fetch(query(country="pk", location="Lahore, PK"))  # Adzuna has no PK
    assert route.called


@respx.mock
def test_jooble_posts_query(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(get_settings(), "jooble_api_key", "k123")
    route = respx.post("https://jooble.org/api/k123").mock(
        return_value=httpx.Response(
            200,
            json={"jobs": [{"id": 1, "link": "https://j/1", "title": "Python Dev",
                            "company": "J", "location": "Berlin", "snippet": "<b>Python</b>",
                            "updated": "2026-10-25T00:00:00", "source": "stepstone"},
                           {"title": "no link"}]},
        )
    )  # fmt: skip
    jobs = JoobleSource().fetch(query(remote_only=True))
    body = json.loads(route.calls[0].request.read())
    assert body["keywords"] == "python developer remote"
    assert "location" not in body  # remote-only searches aren't tied to a city
    assert len(jobs) == 1 and jobs[0].tags == ["stepstone"]


@respx.mock
def test_serpapi_maps_apply_links(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(get_settings(), "serpapi_key", "s")
    respx.get("https://serpapi.com/search.json").mock(
        return_value=httpx.Response(
            200,
            json={"jobs_results": [{"job_id": "x", "title": "Python Dev", "company_name": "G",
                                    "apply_options": [{"link": "https://apply/x"}],
                                    "detected_extensions": {"work_from_home": True}}]},
        )
    )  # fmt: skip
    job = SerpApiSource().fetch(query())[0]
    assert job.url == job.apply_url == "https://apply/x"
    assert job.is_remote is True


@respx.mock
@pytest.mark.parametrize(
    ("status", "code"),
    [(429, "rate_limited"), (401, "auth_failed"), (404, "http_error"), (503, "unavailable")],
)
def test_http_failures_become_source_errors(
    status: int, code: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("tenacity.nap.time.sleep", lambda _s: None)
    respx.get(ArbeitnowSource.URL).mock(return_value=httpx.Response(status))
    with pytest.raises(SourceError) as exc:
        ArbeitnowSource().fetch(query())
    assert exc.value.code == code


def test_jobspy_maps_dataframe_rows(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, Any] = {}

    def fake_scrape(**kwargs: Any) -> pd.DataFrame:
        captured.update(kwargs)
        return pd.DataFrame(
            [
                {"id": "li-1", "job_url": "https://linkedin.com/jobs/view/1", "title": "Python Dev",
                 "company": "L", "location": {"city": "Berlin", "state": None, "country": "Germany"},
                 "description": "**Python** role", "is_remote": False, "min_amount": 70000.0,
                 "max_amount": 90000.0, "interval": "yearly", "currency": "EUR",
                 "date_posted": pd.Timestamp("2026-10-20").date(), "emails": ["hr@l.example"]},
                {"id": "li-2", "job_url": None, "title": "no url"},
            ]
        )  # fmt: skip

    monkeypatch.setattr("jobspy.scrape_jobs", fake_scrape)
    jobs = JobSpySource("linkedin", "LinkedIn", interval=0).fetch(query(results_wanted=80))
    assert captured["site_name"] == ["linkedin"]
    assert captured["results_wanted"] == 50  # capped to stay under LinkedIn's limits
    assert len(jobs) == 1
    job = jobs[0]
    assert job.location == "Berlin, Germany"
    assert (job.salary_min, job.salary_period, job.salary_currency) == (70000.0, "year", "EUR")
    assert job.posted_at is not None and job.emails == ["hr@l.example"]


def test_jobspy_blocked_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    def blocked(**_: Any) -> pd.DataFrame:
        frame = pd.DataFrame(columns=["job_url"])
        frame.attrs = {"errors": {"linkedin": "429"}}
        return frame

    monkeypatch.setattr("jobspy.scrape_jobs", blocked)
    with pytest.raises(SourceError) as exc:
        JobSpySource("linkedin", "LinkedIn", interval=0).fetch(query())
    assert exc.value.code == "blocked"


def test_circuit_breaker_pauses_after_three_failures() -> None:
    assert not source_guard.is_paused("flaky")
    assert source_guard.record_failure("flaky") is False
    source_guard.record_success("flaky")  # success resets the streak
    assert source_guard.record_failure("flaky") is False
    assert source_guard.record_failure("flaky") is False
    assert source_guard.record_failure("flaky") is True
    assert source_guard.is_paused("flaky")
    assert 0 < source_guard.paused_for("flaky") <= 3600


def test_wait_turn_spaces_requests() -> None:
    info = ArbeitnowSource.info
    assert source_guard.wait_turn(info, sleep=False) == 0
    waited = source_guard.wait_turn(info, sleep=False)
    assert 0 < waited <= info.min_interval_seconds
