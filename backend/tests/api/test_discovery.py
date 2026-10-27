from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Job, JobSourceRecord, SearchRun
from app.models.enums import SearchStatus, SearchTrigger
from app.providers.sources import SourceError, set_sources_override
from app.providers.sources.http import _redis
from tests.conftest import FakeMailer, csrf_headers, signed_in
from tests.fakes import FakeSource, raw_job

PREFS: dict[str, Any] = {
    "target_titles": ["Python Developer"],
    "locations": [{"city": "Berlin", "country": "de"}],
    "remote_types": ["remote", "onsite"],
    "sources": ["alpha", "beta"],
    "posted_within_days": 7,
    "results_per_source": 20,
}


@pytest.fixture
def sources() -> Iterator[dict[str, FakeSource]]:
    shared = raw_job("alpha", 0, title="Senior Python Developer", company="Acme Inc")
    alpha = FakeSource("alpha", [raw_job("alpha", 1), raw_job("alpha", 2), shared])
    # Beta returns the same posting as alpha (different URL, same company/title/city).
    beta_dup = raw_job("beta", 0, title="Sr. Python Developer", company="ACME")
    beta = FakeSource("beta", [beta_dup, raw_job("beta", 3, company="Beta GmbH")])
    keyed = FakeSource("keyed", configured=False, default_on=False)
    registry = {"alpha": alpha, "beta": beta, "keyed": keyed}
    set_sources_override(list(registry.values()))
    r = _redis()
    if keys := r.keys("source:*"):
        r.delete(*keys)
    yield registry
    set_sources_override(None)


async def save_prefs(client: AsyncClient, **overrides: Any) -> Any:
    r = await client.put(
        "/api/v1/preferences", json={**PREFS, **overrides}, headers=csrf_headers(client)
    )
    return r


async def start(client: AsyncClient) -> Any:
    return await client.post("/api/v1/searches", headers=csrf_headers(client))


async def test_preferences_defaults_and_validation(
    client: AsyncClient, mailer: FakeMailer, sources: dict[str, FakeSource]
) -> None:
    await signed_in(client, mailer)
    prefs = (await client.get("/api/v1/preferences")).json()
    assert prefs["is_saved"] is False
    assert prefs["sources"] == ["alpha", "beta"]  # default_on sources only

    r = await save_prefs(client, sources=["alpha", "nope"])
    assert r.status_code == 422 and r.json()["code"] == "unknown_source"
    r = await save_prefs(client, locations=[{"city": "Berlin", "country": "Germany"}])
    assert r.status_code == 422  # country must be ISO-2
    r = await save_prefs(client, target_titles=["Python Developer", "python developer"])
    assert r.status_code == 200
    assert r.json()["target_titles"] == ["Python Developer"]  # case-insensitive dedupe
    assert r.json()["is_saved"] is True
    me = (await client.get("/api/v1/users/me")).json()
    assert me["onboarding_step"] == "done"


async def test_sources_list_shows_configuration(
    client: AsyncClient, mailer: FakeMailer, sources: dict[str, FakeSource]
) -> None:
    await signed_in(client, mailer)
    listed = {s["name"]: s for s in (await client.get("/api/v1/sources")).json()}
    assert listed["alpha"]["configured"] is True
    assert listed["keyed"]["configured"] is False and listed["keyed"]["default_on"] is False


async def test_search_requires_preferences(
    client: AsyncClient, mailer: FakeMailer, sources: dict[str, FakeSource]
) -> None:
    await signed_in(client, mailer)
    r = await start(client)
    assert r.status_code == 422 and r.json()["code"] == "search_not_ready"


async def test_search_run_stores_dedupes_and_embeds(
    client: AsyncClient, mailer: FakeMailer, sources: dict[str, FakeSource], db: AsyncSession
) -> None:
    await signed_in(client, mailer)
    await save_prefs(client)
    r = await start(client)
    assert r.status_code == 202, r.text
    run = (await client.get(f"/api/v1/searches/{r.json()['id']}")).json()

    assert run["status"] == "completed", run
    assert run["progress"] == 100 and run["is_active"] is False
    # Each fake source answers both queries (Berlin + remote) with the same 2-3 jobs, and
    # beta repeats alpha's posting: 10 results -> 4 distinct jobs.
    assert run["counts"] == {
        "scraped": 10,
        "new": 4,
        "duplicates": 6,
        "new_for_you": 4,
        "filtered_out": 0,  # no resume yet, so nothing is matched
        "scored": 0,
    }
    assert [s["status"] for s in run["sources"]] == ["ok", "ok"]
    # Berlin onsite + remote-only = 2 queries per source.
    assert len(sources["alpha"].queries) == 2
    assert {q.remote_only for q in sources["alpha"].queries} == {False, True}

    assert await db.scalar(select(func.count()).select_from(Job)) == 4
    shared = await db.scalar(select(Job).where(Job.title == "Senior Python Developer"))
    assert shared is not None and shared.embedding is not None
    srcs = await db.scalars(
        select(JobSourceRecord.source).where(JobSourceRecord.job_id == shared.id)
    )
    assert sorted(srcs) == ["alpha", "beta"]

    page = (await client.get("/api/v1/jobs")).json()
    assert page["total"] == 4 and len(page["items"]) == 4
    card = next(i for i in page["items"] if i["title"] == "Senior Python Developer")
    assert card["sources"] == ["alpha", "beta"]
    assert {"Python", "FastAPI", "PostgreSQL", "AWS"} <= set(card["required_skills"])
    assert card["has_contact_email"] is True and card["min_years_experience"] == 3.0

    # Running again finds the same jobs: nothing new for this user.
    run2 = (await start(client)).json()
    run2 = (await client.get(f"/api/v1/searches/{run2['id']}")).json()
    assert run2["counts"]["new"] == 0 and run2["counts"]["new_for_you"] == 0


async def test_failing_source_gives_partial_run(
    client: AsyncClient, mailer: FakeMailer, sources: dict[str, FakeSource]
) -> None:
    sources["beta"].error = SourceError("blocked", "Beta blocked the request.")
    await signed_in(client, mailer)
    await save_prefs(client, sources=["alpha", "beta", "keyed"])
    run_id = (await start(client)).json()["id"]
    run = (await client.get(f"/api/v1/searches/{run_id}")).json()
    by_name = {s["source"]: s for s in run["sources"]}
    assert run["status"] == "partial"
    assert by_name["alpha"]["status"] == "ok"
    assert by_name["beta"]["status"] == "failed" and by_name["beta"]["error_code"] == "blocked"
    assert by_name["keyed"]["status"] == "skipped"
    assert by_name["keyed"]["error_code"] == "not_configured"
    assert (await client.get("/api/v1/jobs")).json()["total"] == 3


async def test_all_sources_failing_fails_the_run(
    client: AsyncClient, mailer: FakeMailer, sources: dict[str, FakeSource]
) -> None:
    for name in ("alpha", "beta"):
        sources[name].error = SourceError("unavailable", "down")
    await signed_in(client, mailer)
    await save_prefs(client)
    run = (await start(client)).json()
    run = (await client.get(f"/api/v1/searches/{run['id']}")).json()
    assert run["status"] == "failed"


async def test_one_active_search_at_a_time_and_cancel(
    client: AsyncClient, mailer: FakeMailer, sources: dict[str, FakeSource], db: AsyncSession
) -> None:
    await signed_in(client, mailer)
    await save_prefs(client)
    user_id = (await client.get("/api/v1/users/me")).json()["id"]
    running = SearchRun(
        user_id=user_id,
        trigger=SearchTrigger.MANUAL,
        status=SearchStatus.SCRAPING,
        query_snapshot={},
        counts={},
    )
    db.add(running)
    await db.commit()

    r = await start(client)
    assert r.status_code == 409 and r.json()["run_id"] == str(running.id)
    active = (await client.get("/api/v1/searches/active")).json()
    assert active["id"] == str(running.id)

    r = await client.post(f"/api/v1/searches/{running.id}/cancel", headers=csrf_headers(client))
    assert r.json()["status"] == "cancelled"
    assert (await client.get("/api/v1/searches/active")).json() is None
    assert (await start(client)).status_code == 202


async def test_job_list_filters_detail_and_dismiss(
    client: AsyncClient, mailer: FakeMailer, sources: dict[str, FakeSource]
) -> None:
    await signed_in(client, mailer)
    await save_prefs(client)
    await start(client)

    page = (await client.get("/api/v1/jobs", params={"source": "beta"})).json()
    assert page["total"] == 2
    page = (await client.get("/api/v1/jobs", params={"q": "beta gmbh"})).json()
    assert [i["company_name"] for i in page["items"]] == ["Beta GmbH"]
    page = (await client.get("/api/v1/jobs", params={"limit": 3})).json()
    assert len(page["items"]) == 3 and page["has_more"] is True

    job_id = page["items"][0]["id"]
    detail = (await client.get(f"/api/v1/jobs/{job_id}")).json()
    assert "We use Python" in detail["description_text"]
    assert detail["contact_emails"] == ["jobs@acme.example"]
    assert detail["source_links"][0]["url"].startswith("https://")

    r = await client.post(f"/api/v1/jobs/{job_id}/dismiss", headers=csrf_headers(client))
    assert r.status_code == 204
    assert (await client.get("/api/v1/jobs")).json()["total"] == 3
    hidden = (await client.get("/api/v1/jobs", params={"include_dismissed": True})).json()
    assert any(i["id"] == job_id and i["dismissed"] for i in hidden["items"])
    await client.post(f"/api/v1/jobs/{job_id}/undismiss", headers=csrf_headers(client))
    assert (await client.get("/api/v1/jobs")).json()["total"] == 4


async def test_jobs_and_searches_are_private(
    client: AsyncClient, mailer: FakeMailer, sources: dict[str, FakeSource]
) -> None:
    await signed_in(client, mailer)
    await save_prefs(client)
    run_id = (await start(client)).json()["id"]
    job_id = (await client.get("/api/v1/jobs")).json()["items"][0]["id"]

    await client.post("/api/v1/auth/logout", headers=csrf_headers(client))
    await signed_in(client, mailer, email="eve@example.com")
    assert (await client.get(f"/api/v1/jobs/{job_id}")).status_code == 404
    assert (await client.get(f"/api/v1/searches/{run_id}")).status_code == 404
    assert (await client.get("/api/v1/jobs")).json()["total"] == 0
    r = await client.post(f"/api/v1/jobs/{job_id}/dismiss", headers=csrf_headers(client))
    assert r.status_code == 404


async def test_internship_search_and_pay_filter(
    client: AsyncClient, mailer: FakeMailer, sources: dict[str, FakeSource]
) -> None:
    paid = raw_job("alpha", 5, title="Python Intern", company="Paid Co")
    paid.description = "<p>Paid internship with a monthly stipend.</p>"
    unpaid = raw_job("alpha", 6, title="Python Intern", company="Free Co")
    unpaid.description = "<p>This is an unpaid internship.</p>"
    unstated = raw_job("beta", 7, title="Python Internship", company="Quiet Co")
    unstated.description = "<p>Learn Python with us.</p>"
    sources["alpha"].jobs = [paid, unpaid, raw_job("alpha", 1)]  # plus one regular job
    sources["beta"].jobs = [unstated]

    await signed_in(client, mailer)
    await save_prefs(client, target_titles=["Senior Python Developer"])
    r = await client.post(
        "/api/v1/searches", json={"kind": "internships"}, headers=csrf_headers(client)
    )
    assert r.status_code == 202, r.text
    run = (await client.get(f"/api/v1/searches/{r.json()['id']}")).json()
    assert run["kind"] == "internships" and run["status"] == "completed"
    query = sources["alpha"].queries[0]
    assert query.internship and query.search_term == "Python Developer"
    # The regular job the keyword search returned is dropped: only internships are stored.
    assert run["counts"]["new"] == 3

    async def titles(**params: str) -> list[str]:
        page = (await client.get("/api/v1/jobs", params=params)).json()
        return sorted(i["company_name"] for i in page["items"])

    assert await titles(kind="internships") == ["Free Co", "Paid Co", "Quiet Co"]
    assert await titles(kind="internships", pay="paid") == ["Paid Co"]
    assert await titles(kind="internships", pay="unpaid") == ["Free Co"]
    assert await titles(kind="internships", pay="unknown") == ["Quiet Co"]
    assert await titles(kind="jobs") == []

    # A normal search (no body) is still a job search.
    await start(client)
    assert await titles(kind="jobs") == ["Acme Inc"]
