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
from app.domain.extraction_rules import detect_pay, internship_role
from app.domain.normalize import normalize
from app.models.enums import PayStatus
from app.providers.sources import RawJob, SourceQuery
from app.providers.sources.feeds import ArbeitnowSource, role_matches
from app.providers.sources.http import _redis
from app.providers.sources.jobspy_source import JobSpySource
from app.providers.sources.keyed_apis import AdzunaSource, JoobleSource
from app.services.search_pipeline import build_queries

NOW = int(time.time())


def query(**kw: Any) -> SourceQuery:
    base: dict[str, Any] = {
        "search_term": "Backend Engineer",
        "location": "Berlin, DE",
        "country": "de",
        "remote_only": False,
        "posted_within_days": 7,
        "results_wanted": 10,
        "internship": True,
    }
    return SourceQuery(**{**base, **kw})


@pytest.fixture(autouse=True)
def clear_source_keys() -> Iterator[None]:
    def wipe() -> None:
        r = _redis()
        for pattern in ("source-cache:*", "source:*"):
            if keys := r.keys(pattern):
                r.delete(*keys)

    wipe()
    yield
    wipe()


def test_internship_role_drops_seniority() -> None:
    assert internship_role("Senior Backend Engineer") == "Backend Engineer"
    assert internship_role("Sr. Data Analyst") == "Data Analyst"
    assert internship_role("Head of Marketing") == "Marketing"
    assert internship_role("Lead") == "Lead"  # nothing left: keep the original


@pytest.mark.parametrize(
    ("text", "has_salary", "expected"),
    [
        ("This is an unpaid internship for students.", False, PayStatus.UNPAID),
        ("Volunteer position, no stipend.", False, PayStatus.UNPAID),
        ("For academic credit only.", False, PayStatus.UNPAID),
        ("Monthly stipend of PKR 40,000.", False, PayStatus.PAID),
        ("Paid internship, 3 months.", False, PayStatus.PAID),
        ("$25/hr, 20 hours a week.", False, PayStatus.PAID),
        ("Great team, lots of learning.", True, PayStatus.PAID),
        ("Great team, lots of learning.", False, PayStatus.UNKNOWN),
        ("Benefits: 5 days unpaid leave. Stipend provided.", False, PayStatus.PAID),
    ],
)
def test_detect_pay(text: str, has_salary: bool, expected: PayStatus) -> None:
    assert detect_pay("Backend Intern", text, has_salary) == expected


def test_normalize_labels_pay() -> None:
    raw = RawJob(
        source="x",
        source_job_id="1",
        url="https://x/1",
        title="Software Engineering Intern",
        company="X",
        description="Unpaid internship, remote.",
    )
    job = normalize(raw)
    assert job.pay_status == PayStatus.UNPAID
    assert job.employment_type.value == "internship"


def test_build_queries_for_internships() -> None:
    snapshot = {
        "kind": "internships",
        "target_titles": ["Senior Backend Engineer", "Backend Engineer"],
        "locations": [{"city": "Lahore", "country": "pk"}],
        "remote_types": ["onsite"],
    }
    queries = build_queries(snapshot)
    # Both titles become the same role, so there's one query, flagged as an internship.
    assert [(q.search_term, q.internship) for q in queries] == [("Backend Engineer", True)]
    jobs = build_queries({**snapshot, "kind": "jobs"})
    assert len(jobs) == 2 and not any(q.internship for q in jobs)


def test_role_matching_is_looser_for_internships() -> None:
    assert role_matches("Backend Engineer", "Praktikum Backend Development")
    assert not role_matches("Backend Engineer", "Frontend Intern")
    assert role_matches("Engineer", "Engineer Intern")  # all words generic: plain match


@respx.mock
def test_arbeitnow_keeps_only_matching_internships() -> None:
    feed = {
        "data": [
            {"slug": "a", "title": "Backend Intern", "company_name": "A", "url": "https://a",
             "location": "Berlin", "remote": False, "tags": [], "job_types": [],
             "created_at": NOW},
            {"slug": "b", "title": "Backend Developer", "company_name": "B", "url": "https://b",
             "location": "Berlin", "remote": False, "tags": [], "job_types": ["Internship"],
             "created_at": NOW},
            {"slug": "c", "title": "Backend Engineer", "company_name": "C", "url": "https://c",
             "location": "Berlin", "remote": False, "tags": [], "job_types": ["Full Time"],
             "created_at": NOW},
            {"slug": "d", "title": "Marketing Intern", "company_name": "D", "url": "https://d",
             "location": "Berlin", "remote": False, "tags": [], "job_types": [],
             "created_at": NOW},
        ],
        "links": {"next": None},
    }  # fmt: skip
    respx.get(ArbeitnowSource.URL).mock(return_value=httpx.Response(200, json=feed))
    jobs = ArbeitnowSource().fetch(query())
    assert [j.company for j in jobs] == ["A", "B"]


@respx.mock
def test_keyed_apis_ask_for_internships(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = get_settings()
    monkeypatch.setattr(settings, "adzuna_app_id", "id")
    monkeypatch.setattr(settings, "adzuna_app_key", "key")
    monkeypatch.setattr(settings, "jooble_api_key", "k1")
    adzuna = respx.get("https://api.adzuna.com/v1/api/jobs/de/search/1").mock(
        return_value=httpx.Response(200, json={"results": []})
    )
    jooble = respx.post("https://jooble.org/api/k1").mock(
        return_value=httpx.Response(200, json={"jobs": []})
    )
    AdzunaSource().fetch(query())
    JoobleSource().fetch(query())
    params = adzuna.calls[0].request.url.params
    assert params["what"] == "Backend Engineer"
    assert params["what_or"] == "intern internship trainee"
    assert json.loads(jooble.calls[0].request.read())["keywords"] == "Backend Engineer intern"


def test_jobspy_internship_search(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[dict[str, Any]] = []

    def fake_scrape(**kwargs: Any) -> pd.DataFrame:
        calls.append(kwargs)
        return pd.DataFrame([])

    monkeypatch.setattr("jobspy.scrape_jobs", fake_scrape)
    JobSpySource("linkedin", "LinkedIn", interval=0).fetch(query())
    JobSpySource("indeed", "Indeed", interval=0).fetch(query())
    linkedin, indeed = calls
    assert linkedin["job_type"] == "internship"
    assert linkedin["search_term"] == "Backend Engineer intern"
    assert "hours_old" in linkedin
    assert "hours_old" not in indeed  # Indeed can't filter by type and date together
