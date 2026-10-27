from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import UsageEvent
from app.models.enums import UsageFeature
from app.prompts.registry import RenderedPrompt
from app.providers.llm import LLMUnavailable
from app.providers.llm.fake import FakeLLM
from app.providers.sources import set_sources_override
from app.providers.sources.http import _redis
from tests.api.test_matching import PREFS, score_by_title
from tests.api.test_resumes import upload
from tests.conftest import FakeMailer, csrf_headers, signed_in
from tests.fakes import FakeSource, raw_job
from tests.fixtures import make_pdf, parsed_resume_json

FILLER = "I enjoy building reliable backend systems with clear tests and calm on-call. "


def words(n: int) -> str:
    out = (FILLER * (n // 13 + 1)).split()[:n]
    return " ".join(out).rstrip(".") + "."


class Writer:
    """Fake AI for the writing prompts; tests tweak `email_body` / `claims`."""

    def __init__(self) -> None:
        self.email_body = (
            "At Analytical Engines I built FastAPI services handling 2M requests per day on "
            "AWS, and your Python and PostgreSQL stack is what I use daily. " + words(60)
        )
        self.cover_body = "Your team uses Python, FastAPI and PostgreSQL on AWS. " + words(270)
        self.claims: list[dict[str, str]] = [
            {
                "claim": "Built FastAPI services handling 2M requests per day",
                "supporting_quote": "Built FastAPI services handling 2M requests per day on AWS",
                "where": "email",
            }
        ]

    def __call__(self, prompt: RenderedPrompt) -> dict[str, Any]:
        kind = prompt.spec.id
        if kind == "match_score":
            return score_by_title(prompt)
        if kind in ("application_email", "cover_letter"):
            body = self.email_body if kind == "application_email" else self.cover_body
            return {
                "greeting": "Hello Acme team,",
                "body": body,
                "skills_used": ["Python", "FastAPI"],
                "achievement_ref": "b1",
                "job_detail": "PostgreSQL on AWS",
            }
        if kind == "resume_tweaks":
            return {
                "tweaks": [
                    {"bullet_id": "b1", "suggested": "Built Python FastAPI services serving 2M requests a day on AWS",
                     "rationale": "Leads with the job's stack", "emphasized_skills": ["Python"]},
                    {"bullet_id": "b99", "suggested": "Invented", "rationale": "", "emphasized_skills": []},
                ]
            }  # fmt: skip
        if kind == "claim_verify":
            return {"claims": self.claims}
        raise AssertionError(f"unexpected prompt {kind}")


@pytest.fixture
def writer(fake_llm: FakeLLM) -> Writer:
    w = Writer()
    fake_llm.responder = w
    return w


@pytest.fixture
def source() -> Iterator[FakeSource]:
    fake = FakeSource("alpha", [raw_job("alpha", 1, title="Python Developer", company="Acme Inc")])
    set_sources_override([fake])
    r = _redis()
    if keys := r.keys("source:*"):
        r.delete(*keys)
    yield fake
    set_sources_override(None)


async def setup(client: AsyncClient, mailer: FakeMailer, fake_llm: FakeLLM) -> str:
    """Signed-in user with a parsed resume and one discovered job; returns the job id."""
    await signed_in(client, mailer)
    fake_llm.queue(parsed_resume_json())
    assert (await upload(client, make_pdf()))["http"] == 202
    await client.put("/api/v1/preferences", json=PREFS, headers=csrf_headers(client))
    await client.post("/api/v1/searches", headers=csrf_headers(client))
    job_id: str = (await client.get("/api/v1/jobs")).json()["items"][0]["id"]
    return job_id


async def prepare(client: AsyncClient, job_id: str, **body: Any) -> dict[str, Any]:
    r = await client.post(
        f"/api/v1/jobs/{job_id}/prepare-application", json=body, headers=csrf_headers(client)
    )
    assert r.status_code == 202, r.text
    app: dict[str, Any] = (await client.get(f"/api/v1/applications/{r.json()['id']}")).json()
    return app


async def llm_calls(db: AsyncSession, feature: UsageFeature) -> int:
    n = await db.scalar(
        select(func.count()).select_from(UsageEvent).where(UsageEvent.feature == feature)
    )
    return int(n or 0)


async def test_prepare_writes_checked_drafts(
    client: AsyncClient,
    mailer: FakeMailer,
    fake_llm: FakeLLM,
    writer: Writer,
    source: FakeSource,
    db: AsyncSession,
) -> None:
    job_id = await setup(client, mailer, fake_llm)
    calls_before = len(fake_llm.calls)
    app = await prepare(client, job_id, tone="friendly")

    assert app["status"] == "ready" and app["last_error"] is None
    assert app["contact_email"] == "jobs@acme.example"  # found in the job description
    assert app["email_source"] == "job_description" and app["channel"] == "email"

    email = app["email"]
    assert email["content"]["subject"] == "Application: Python Developer 1, Ada Lovelace"
    assert email["content"]["body"].startswith("Hello Acme team,\n\n")
    assert email["content"]["signature"].startswith("Thanks,\nAda Lovelace")  # friendly tone
    assert email["flags"] == [] and email["verified"] is True
    assert 60 <= email["word_count"] <= 152
    assert app["cover_letter"]["word_count"] >= 250
    assert app["flags_blocked"] is False

    # Writing prompts see the fact sheet, never contact details.
    prompts = fake_llm.calls[calls_before:]
    assert [p.spec.id for p in prompts] == ["application_email", "cover_letter", "claim_verify"]
    assert all("555 010" not in p.user and "ada@example.com" not in p.user for p in prompts)
    assert await llm_calls(db, UsageFeature.GENERATE) == 2
    assert await llm_calls(db, UsageFeature.VERIFY) == 1

    job = (await client.get(f"/api/v1/jobs/{job_id}")).json()
    assert job["application"] == {"id": app["id"], "status": "ready"}


async def test_fabrications_block_until_fixed_or_confirmed(
    client: AsyncClient,
    mailer: FakeMailer,
    fake_llm: FakeLLM,
    writer: Writer,
    source: FakeSource,
) -> None:
    job_id = await setup(client, mailer, fake_llm)
    writer.email_body = "I led Rust services that cut costs by 40% across 12 teams. " + words(70)
    writer.claims = [{"claim": "Led Rust services", "supporting_quote": "", "where": "email"}]
    app = await prepare(client, job_id)

    flags = {(f["source"], f["text"], f["severity"]) for f in app["email"]["flags"]}
    assert ("skills", "Rust", "block") in flags
    assert ("numbers", "40%", "block") in flags
    assert ("numbers", "12", "block") in flags
    assert ("verifier", "Led Rust services", "warn") in flags
    assert app["flags_blocked"] is True and app["flags_acknowledged"] is False

    r = await client.post(
        f"/api/v1/applications/{app['id']}/mark-applied", json={}, headers=csrf_headers(client)
    )
    assert r.status_code == 409 and r.json()["code"] == "flags_not_acknowledged"

    # Editing the text re-runs the fast checks right away.
    fixed = "Hello Acme team,\n\nI built FastAPI services handling 2M requests per day. " + words(
        70
    )
    r = await client.patch(
        f"/api/v1/applications/{app['id']}",
        json={"email_body": fixed},
        headers=csrf_headers(client),
    )
    edited = r.json()
    assert edited["email"]["flags"] == [] and edited["email"]["edited_by_user"] is True
    assert edited["email"]["verified"] is False  # needs a fresh AI fact-check
    assert edited["flags_blocked"] is False

    r = await client.post(
        f"/api/v1/applications/{app['id']}/mark-applied",
        json={"channel": "email"},
        headers=csrf_headers(client),
    )
    applied = r.json()
    assert applied["status"] == "applied" and applied["channel"] == "email"
    assert applied["sent_at"] is not None and applied["follow_up_at"] is not None
    r = await client.post(
        f"/api/v1/jobs/{job_id}/prepare-application", json={}, headers=csrf_headers(client)
    )
    assert r.status_code == 409 and r.json()["code"] == "already_applied"


async def test_acknowledging_flags_allows_applying(
    client: AsyncClient,
    mailer: FakeMailer,
    fake_llm: FakeLLM,
    writer: Writer,
    source: FakeSource,
) -> None:
    job_id = await setup(client, mailer, fake_llm)
    writer.email_body = "I know Rust well. " + words(70)
    app = await prepare(client, job_id)
    assert app["flags_blocked"] is True
    r = await client.post(
        f"/api/v1/applications/{app['id']}/acknowledge-flags", headers=csrf_headers(client)
    )
    assert r.json()["flags_acknowledged"] is True
    r = await client.post(
        f"/api/v1/applications/{app['id']}/mark-applied",
        json={"channel": "site"},
        headers=csrf_headers(client),
    )
    assert r.json()["status"] == "applied" and r.json()["channel"] == "site"


async def test_long_email_is_retried_then_trimmed(
    client: AsyncClient,
    mailer: FakeMailer,
    fake_llm: FakeLLM,
    writer: Writer,
    source: FakeSource,
) -> None:
    job_id = await setup(client, mailer, fake_llm)
    writer.email_body = words(80) + " " + words(80) + " " + words(80)
    app = await prepare(client, job_id, kinds=["email"])
    email_prompts = [p for p in fake_llm.calls if p.spec.id == "application_email"]
    assert len(email_prompts) == 2  # one automatic retry with the word count
    assert "must be between 60 and 150 words" in email_prompts[1].system
    body_words = app["email"]["word_count"]
    assert body_words <= 152  # 150 + the greeting
    assert any(f["source"] == "length" for f in app["email"]["flags"])
    assert app["cover_letter"] is None


async def test_versions_tweaks_contact_and_regenerate(
    client: AsyncClient,
    mailer: FakeMailer,
    fake_llm: FakeLLM,
    writer: Writer,
    source: FakeSource,
) -> None:
    job_id = await setup(client, mailer, fake_llm)
    app = await prepare(client, job_id, kinds=["email", "resume_tweaks"])
    tweaks = app["resume_tweaks"]["content"]["tweaks"]
    assert [t["bullet_id"] for t in tweaks] == ["b1"]  # made-up bullet ids are dropped
    assert tweaks[0]["original"].startswith("Built FastAPI services")

    first_email = app["email"]["id"]
    r = await client.post(
        f"/api/v1/applications/{app['id']}/regenerate",
        json={"kind": "email", "tone": "concise"},
        headers=csrf_headers(client),
    )
    assert r.status_code == 202
    app = (await client.get(f"/api/v1/applications/{app['id']}")).json()
    assert len(app["versions"]["email"]) == 2 and app["email"]["tone"] == "concise"
    assert app["email"]["content"]["signature"].startswith("Best,")

    r = await client.post(
        f"/api/v1/applications/{app['id']}/use-version",
        json={"draft_id": first_email},
        headers=csrf_headers(client),
    )
    assert r.json()["email"]["tone"] == "formal" and len(r.json()["versions"]["email"]) == 3

    r = await client.patch(
        f"/api/v1/applications/{app['id']}",
        json={"contact_email": "Jane@Acme.example", "notes": "Met at a meetup"},
        headers=csrf_headers(client),
    )
    out = r.json()
    assert out["contact_email"] == "jane@acme.example" and out["email_source"] == "manual"
    assert out["notes"] == "Met at a meetup"
    # A manual contact survives regenerating.
    await client.post(
        f"/api/v1/applications/{app['id']}/regenerate",
        json={"kind": "cover_letter"},
        headers=csrf_headers(client),
    )
    again = (await client.get(f"/api/v1/applications/{app['id']}")).json()
    assert again["contact_email"] == "jane@acme.example"
    assert [e["to_status"] for e in again["events"]][:2] == ["ready", "drafting"]


async def test_ai_outage_and_save_for_later(
    client: AsyncClient,
    mailer: FakeMailer,
    fake_llm: FakeLLM,
    writer: Writer,
    source: FakeSource,
) -> None:
    job_id = await setup(client, mailer, fake_llm)
    r = await client.post(f"/api/v1/jobs/{job_id}/save", headers=csrf_headers(client))
    assert r.json()["status"] == "saved" and r.json()["email"] is None
    listed = (await client.get("/api/v1/applications")).json()
    assert [a["status"] for a in listed] == ["saved"]

    fake_llm.queue(LLMUnavailable("busy"))
    app = await prepare(client, job_id)
    assert app["status"] == "ready" and "overloaded" in app["last_error"]
    assert app["email"] is None


async def test_needs_a_resume_and_ownership(
    client: AsyncClient, mailer: FakeMailer, fake_llm: FakeLLM, source: FakeSource
) -> None:
    await signed_in(client, mailer)
    await client.put("/api/v1/preferences", json=PREFS, headers=csrf_headers(client))
    await client.post("/api/v1/searches", headers=csrf_headers(client))
    job_id = (await client.get("/api/v1/jobs")).json()["items"][0]["id"]
    r = await client.post(
        f"/api/v1/jobs/{job_id}/prepare-application", json={}, headers=csrf_headers(client)
    )
    assert r.status_code == 422 and r.json()["code"] == "no_active_resume"
    saved = (await client.post(f"/api/v1/jobs/{job_id}/save", headers=csrf_headers(client))).json()

    await client.post("/api/v1/auth/logout", headers=csrf_headers(client))
    await signed_in(client, mailer, email="eve@example.com")
    assert (await client.get(f"/api/v1/applications/{saved['id']}")).status_code == 404


async def test_gmail_connect_link_and_status(client: AsyncClient, mailer: FakeMailer) -> None:
    await signed_in(client, mailer)
    status = (await client.get("/api/v1/integrations")).json()
    assert status["gmail"]["status"] == "disconnected" and status["google_configured"] is True
    r = await client.get("/api/v1/integrations/gmail/connect")
    assert r.json()["url"].startswith("https://accounts.google.com/o/oauth2/v2/auth?")
    assert "g_connect_state" in r.headers["set-cookie"]
    # A callback without the state cookie (or with a wrong state) is refused.
    client.cookies.delete("g_connect_state")
    r = await client.get("/api/v1/integrations/gmail/callback?code=x&state=y")
    assert r.status_code == 302 and r.headers["location"].endswith("/settings?gmail=expired")
