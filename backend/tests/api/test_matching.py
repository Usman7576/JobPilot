from __future__ import annotations

import json
import re
from collections.abc import Iterator
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import JobMatch, UsageEvent
from app.models.enums import UsageFeature
from app.prompts.registry import RenderedPrompt
from app.providers.llm import LLMQuotaExhausted, LLMUnavailable
from app.providers.llm.fake import FakeLLM
from app.providers.sources import set_sources_override
from app.providers.sources.http import _redis
from tests.api.test_resumes import upload
from tests.conftest import FakeMailer, csrf_headers, signed_in
from tests.fakes import FakeSource, raw_job
from tests.fixtures import make_pdf, parsed_resume_json

PREFS: dict[str, Any] = {
    "target_titles": ["Python Developer"],
    "locations": [{"city": "Berlin", "country": "de"}],
    "remote_types": ["remote", "onsite", "hybrid"],
    "exclude_companies": ["Bad Corp"],
    "sources": ["alpha"],
}
_JOB = re.compile(r'<job ref="(j\d+)">\n(.*?)\n</job>', re.S)


def score_by_title(prompt: RenderedPrompt) -> dict[str, Any]:
    """Fake AI: Python jobs are great fits, everything else is weak."""
    results = []
    for ref, body in _JOB.findall(prompt.user):
        good = "python" in json.loads(body)["title"].lower()
        s = 90 if good else 40
        results.append(
            {
                "job_ref": ref,
                "skills_match": s,
                "experience_match": s,
                "seniority_fit": s,
                "domain_relevance": s,
                "matched_skills": ["python", "Rust"] if good else [],
                "missing_skills": ["Terraform"],
                "red_flags": [],
                "why_good_fit": "You build Python APIs." if good else "Different stack.",
                "apply_recommendation": "strong_apply" if good else "skip",
                "overall_score": 3,  # ignored: computed in code
            }
        )
    return {"results": results}


@pytest.fixture
def source() -> Iterator[FakeSource]:
    jobs = [
        raw_job("alpha", 1, title="Python Developer", company="Acme Inc"),
        raw_job("alpha", 2, title="Java Developer", company="Beta GmbH"),
        raw_job("alpha", 3, title="Python Engineer", company="Bad Corp"),
    ]
    fake = FakeSource("alpha", jobs)
    set_sources_override([fake])
    r = _redis()
    if keys := r.keys("source:*"):
        r.delete(*keys)
    yield fake
    set_sources_override(None)


async def setup_user(client: AsyncClient, mailer: FakeMailer, fake_llm: FakeLLM) -> str:
    await signed_in(client, mailer)
    fake_llm.queue(parsed_resume_json())
    resume = await upload(client, make_pdf())
    assert resume["http"] == 202
    r = await client.put("/api/v1/preferences", json=PREFS, headers=csrf_headers(client))
    assert r.status_code == 200, r.text
    return str(resume["id"])


async def search(client: AsyncClient) -> dict[str, Any]:
    r = await client.post("/api/v1/searches", headers=csrf_headers(client))
    assert r.status_code == 202, r.text
    run: dict[str, Any] = (await client.get(f"/api/v1/searches/{r.json()['id']}")).json()
    return run


async def score_calls(db: AsyncSession) -> int:
    count = await db.scalar(
        select(func.count()).select_from(UsageEvent).where(UsageEvent.feature == UsageFeature.SCORE)
    )
    return int(count or 0)


async def test_search_ranks_and_explains_matches(
    client: AsyncClient,
    mailer: FakeMailer,
    fake_llm: FakeLLM,
    source: FakeSource,
    db: AsyncSession,
) -> None:
    await setup_user(client, mailer, fake_llm)
    fake_llm.responder = score_by_title
    run = await search(client)
    assert run["status"] == "completed", run
    assert run["counts"]["scored"] == 2 and run["counts"]["filtered_out"] == 1
    assert await score_calls(db) == 1  # both jobs scored in one request

    prompt = fake_llm.calls[-1]
    assert "Ada Lovelace" not in prompt.user and "ada@example.com" not in prompt.user

    page = (await client.get("/api/v1/jobs")).json()
    assert page["has_resume"] is True and page["filtered_out"] == 1
    assert [i["company_name"] for i in page["items"]] == ["Acme Inc", "Beta GmbH"]
    top = page["items"][0]["match"]
    assert top["stage"] == "scored" and top["recommendation"] == "strong_apply"
    assert top["overall_score"] >= 80  # LLM's own "overall_score" was ignored

    hidden = (await client.get("/api/v1/jobs", params={"include_filtered": True})).json()
    bad = next(i for i in hidden["items"] if i["company_name"] == "Bad Corp")
    assert bad["match"]["hard_filter_reasons"] == ["excluded_company"]
    assert bad["match"]["overall_score"] is None  # filtered jobs are never sent to the AI

    strong = (await client.get("/api/v1/jobs", params={"min_score": 80})).json()
    assert strong["total"] == 1

    detail = (await client.get(f"/api/v1/jobs/{page['items'][0]['id']}")).json()
    match = detail["match"]
    assert set(match["breakdown"]) == {
        "skills_match",
        "experience_match",
        "seniority_fit",
        "domain_relevance",
        "location_fit",
    }
    assert match["matched_skills"] == ["Python"]
    assert "Rust" in match["missing_skills"]  # not on the resume, so it can't be "matched"
    assert match["why_good_fit"] == "You build Python APIs."

    # A second run finds the same jobs: cached scores, no new AI requests.
    await search(client)
    assert await score_calls(db) == 1
    estimate = (await client.get("/api/v1/searches/estimate")).json()
    assert estimate == {
        "jobs_to_score": 0,
        "llm_requests": 0,
        "requests_left_today": None,
        "has_resume": True,
    }

    # Rescore one job on request.
    r = await client.post(
        f"/api/v1/jobs/{page['items'][1]['id']}/rescore", headers=csrf_headers(client)
    )
    assert r.status_code == 202
    assert await score_calls(db) == 2


async def test_profile_edit_scores_the_new_version_only(
    client: AsyncClient,
    mailer: FakeMailer,
    fake_llm: FakeLLM,
    source: FakeSource,
    db: AsyncSession,
) -> None:
    rid = await setup_user(client, mailer, fake_llm)
    fake_llm.responder = score_by_title
    await search(client)
    assert await score_calls(db) == 1

    resume = (await client.get(f"/api/v1/resumes/{rid}")).json()
    profile = {**resume["profile"], "summary": "Python backend engineer."}
    r = await client.put(
        f"/api/v1/resumes/{rid}/profile", json=profile, headers=csrf_headers(client)
    )
    assert r.status_code == 200 and r.json()["profile_version"] == 2
    # The new version was matched right away; version 1's rows are kept.
    assert await score_calls(db) == 2
    versions = await db.scalars(select(JobMatch.profile_version).distinct())
    assert sorted(versions) == [1, 2]
    page = (await client.get("/api/v1/jobs")).json()
    assert page["items"][0]["match"]["stage"] == "scored"


@pytest.mark.parametrize(
    ("error", "note"),
    [(LLMQuotaExhausted("daily"), "daily limit"), (LLMUnavailable("503"), "overloaded")],
)
async def test_ai_outage_leaves_jobs_ranked_but_unscored(
    client: AsyncClient,
    mailer: FakeMailer,
    fake_llm: FakeLLM,
    source: FakeSource,
    error: Exception,
    note: str,
) -> None:
    await setup_user(client, mailer, fake_llm)
    fake_llm.queue(error)
    run = await search(client)
    assert run["status"] == "completed"
    assert note in run["stage_detail"]
    page = (await client.get("/api/v1/jobs")).json()
    assert page["total"] == 2
    assert all(i["match"]["stage"] == "stage1" for i in page["items"])
    assert all(i["match"]["similarity"] is not None for i in page["items"])
    detail = (await client.get(f"/api/v1/jobs/{page['items'][0]['id']}")).json()
    assert note in detail["match"]["failure_reason"]
    # The next search tries the unscored jobs again.
    fake_llm.responder = score_by_title
    await search(client)
    page = (await client.get("/api/v1/jobs")).json()
    assert all(i["match"]["stage"] == "scored" for i in page["items"])


async def test_no_resume_means_no_scores(
    client: AsyncClient, mailer: FakeMailer, fake_llm: FakeLLM, source: FakeSource
) -> None:
    await signed_in(client, mailer)
    await client.put("/api/v1/preferences", json=PREFS, headers=csrf_headers(client))
    run = await search(client)
    assert run["status"] == "completed" and "resume" in run["stage_detail"].lower()
    page = (await client.get("/api/v1/jobs")).json()
    assert page["has_resume"] is False and page["items"][0]["match"] is None
    assert fake_llm.calls == []
    r = await client.post(
        f"/api/v1/jobs/{page['items'][0]['id']}/rescore", headers=csrf_headers(client)
    )
    assert r.status_code == 422 and r.json()["code"] == "no_active_resume"
