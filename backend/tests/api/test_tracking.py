from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Application
from app.prompts.registry import RenderedPrompt
from app.providers.llm.fake import FakeLLM
from app.providers.sources import set_sources_override
from app.providers.sources.http import _redis
from tests.api.test_applications import Writer, prepare, setup, words
from tests.conftest import FakeMailer, csrf_headers
from tests.fakes import FakeSource, raw_job


class TrackingWriter(Writer):
    """Also answers the follow-up prompt."""

    def __call__(self, prompt: RenderedPrompt) -> dict[str, Any]:
        if prompt.spec.id == "follow_up":
            return {
                "greeting": "Hello Acme team,",
                "body": "I applied for the Python Developer role last week and I'm still very "
                "interested. I built FastAPI services handling 2M requests per day. " + words(30),
                "skills_used": ["FastAPI"],
                "achievement_ref": "b1",
                "job_detail": "",
            }
        return super().__call__(prompt)


@pytest.fixture
def writer(fake_llm: FakeLLM) -> TrackingWriter:
    w = TrackingWriter()
    fake_llm.responder = w
    return w


@pytest.fixture
def source() -> Iterator[FakeSource]:
    fake = FakeSource(
        "alpha",
        [
            raw_job("alpha", 1, title="Python Developer", company="Acme Inc"),
            raw_job("alpha", 2, title="Python Engineer", company="Beta GmbH"),
            raw_job("alpha", 3, title="Java Developer", company="Gamma AG"),
        ],
    )
    set_sources_override([fake])
    r = _redis()
    if keys := r.keys("source:*"):
        r.delete(*keys)
    yield fake
    set_sources_override(None)


async def save(client: AsyncClient, job_id: str) -> str:
    r = await client.post(f"/api/v1/jobs/{job_id}/save", headers=csrf_headers(client))
    app_id: str = r.json()["id"]
    return app_id


async def move(client: AsyncClient, app_id: str, column: str, **extra: Any) -> Any:
    return await client.post(
        f"/api/v1/applications/{app_id}/move",
        json={"column": column, **extra},
        headers=csrf_headers(client),
    )


async def jobs(client: AsyncClient) -> list[str]:
    items = (await client.get("/api/v1/jobs")).json()["items"]
    return [i["id"] for i in items]


async def test_board_moves_set_status_and_dates(
    client: AsyncClient,
    mailer: FakeMailer,
    fake_llm: FakeLLM,
    writer: TrackingWriter,
    source: FakeSource,
) -> None:
    await setup(client, mailer, fake_llm)
    first, second, third = (await jobs(client))[:3]
    a, b, c = await save(client, first), await save(client, second), await save(client, third)

    board = (await client.get("/api/v1/applications/board")).json()
    assert {card["column"] for card in board} == {"saved"}

    card = (await move(client, a, "applied")).json()
    assert card["status"] == "applied" and card["channel"] == "site"
    assert card["sent_at"] is not None and card["follow_up_at"] is not None
    assert card["follow_up_due"] is False

    # Reorder inside a column: b goes between nothing and a, so before it.
    await move(client, b, "applied", after_id=a)
    applied = [
        x
        for x in (await client.get("/api/v1/applications/board")).json()
        if x["column"] == "applied"
    ]
    assert [x["id"] for x in applied] == [b, a]

    replied = (await move(client, a, "replied")).json()
    assert replied["last_reply_at"] is not None and replied["follow_up_at"] is None

    rejected = (await move(client, c, "rejected", withdrawn=True)).json()
    assert rejected["status"] == "withdrawn" and rejected["column"] == "rejected"

    back = (await move(client, b, "saved")).json()
    assert back["status"] == "saved" and back["sent_at"] is None

    app = (await client.get(f"/api/v1/applications/{a}")).json()
    assert [e["to_status"] for e in app["events"]][:2] == ["replied", "applied"]


async def test_dragging_to_applied_respects_unchecked_claims(
    client: AsyncClient,
    mailer: FakeMailer,
    fake_llm: FakeLLM,
    writer: TrackingWriter,
    source: FakeSource,
) -> None:
    job_id = await setup(client, mailer, fake_llm)
    writer.email_body = "I know Rust well. " + words(70)
    app = await prepare(client, job_id)
    r = await move(client, app["id"], "applied")
    assert r.status_code == 409 and r.json()["code"] == "flags_not_acknowledged"
    back = (await move(client, app["id"], "saved")).json()
    assert back["status"] == "ready"  # it has drafts


async def test_follow_up_reminders_drafts_and_counting(
    client: AsyncClient,
    mailer: FakeMailer,
    fake_llm: FakeLLM,
    writer: TrackingWriter,
    source: FakeSource,
    db: AsyncSession,
) -> None:
    job_id = await setup(client, mailer, fake_llm)
    app = await prepare(client, job_id, kinds=["email"])
    r = await client.post(
        f"/api/v1/applications/{app['id']}/mark-applied", json={}, headers=csrf_headers(client)
    )
    assert r.json()["status"] == "applied"

    # Nothing due yet.
    notes = (await client.get("/api/v1/notifications")).json()
    assert not any(n["kind"] == "follow_up_due" for n in notes["items"])

    await db.execute(
        update(Application)
        .where(Application.job_id == job_id)
        .values(follow_up_at=datetime.now(UTC) - timedelta(hours=1))
    )
    await db.commit()
    for _ in range(2):  # created once, however often it's checked
        notes = (await client.get("/api/v1/notifications")).json()
    due = [n for n in notes["items"] if n["kind"] == "follow_up_due"]
    assert len(due) == 1 and due[0]["link"] == f"/applications/{app['id']}"
    company = (await client.get(f"/api/v1/jobs/{job_id}")).json()["company_name"]
    assert due[0]["title"] == f"Follow up with {company}"
    board = (await client.get("/api/v1/applications/board")).json()
    assert next(c for c in board if c["id"] == app["id"])["follow_up_due"] is True

    r = await client.post(
        f"/api/v1/applications/{app['id']}/follow-up-draft",
        json={"tone": "friendly"},
        headers=csrf_headers(client),
    )
    assert r.status_code == 202
    full = (await client.get(f"/api/v1/applications/{app['id']}")).json()
    follow = full["follow_up"]
    assert follow["content"]["subject"] == "Re: " + app["email"]["content"]["subject"]
    assert follow["content"]["signature"].startswith("Thanks,")
    assert follow["flags"] == [] and follow["verified"] is True
    assert full["status"] == "applied"  # writing a follow-up never changes the status

    first = (
        await client.post(
            f"/api/v1/applications/{app['id']}/follow-up-sent", headers=csrf_headers(client)
        )
    ).json()
    assert first["follow_up_count"] == 1 and first["follow_up_due"] is False
    second = (
        await client.post(
            f"/api/v1/applications/{app['id']}/follow-up-sent", headers=csrf_headers(client)
        )
    ).json()
    assert second["follow_up_count"] == 2 and second["follow_up_at"] is None  # two at most

    await client.post("/api/v1/notifications/read", json={}, headers=csrf_headers(client))
    assert (await client.get("/api/v1/notifications")).json()["unread"] == 0


async def test_follow_up_needs_an_application_sent(
    client: AsyncClient,
    mailer: FakeMailer,
    fake_llm: FakeLLM,
    writer: TrackingWriter,
    source: FakeSource,
) -> None:
    await setup(client, mailer, fake_llm)
    app_id = await save(client, (await jobs(client))[0])
    r = await client.post(
        f"/api/v1/applications/{app_id}/follow-up-draft", json={}, headers=csrf_headers(client)
    )
    assert r.status_code == 409 and r.json()["code"] == "not_applied"


async def test_search_notifies_strong_matches_and_dashboard_counts(
    client: AsyncClient,
    mailer: FakeMailer,
    fake_llm: FakeLLM,
    writer: TrackingWriter,
    source: FakeSource,
) -> None:
    await setup(client, mailer, fake_llm)
    notes = (await client.get("/api/v1/notifications")).json()
    strong = [n for n in notes["items"] if n["kind"] == "strong_matches"]
    assert strong and strong[0]["title"] == "2 strong matches found"  # the two Python jobs
    assert notes["unread"] >= 1

    first, second, third = (await jobs(client))[:3]
    a, b = await save(client, first), await save(client, second)
    await save(client, third)
    await move(client, a, "applied")
    await move(client, b, "applied")
    await move(client, b, "interview")

    dash = (await client.get("/api/v1/dashboard")).json()
    stats = dash["stats"]
    assert stats["jobs_found"] == 3
    assert stats["applied"] == 2 and stats["replied"] == 1 and stats["interviews"] == 1
    assert stats["reply_rate"] == 0.5
    assert stats["avg_match_score"] is not None
    assert [s["step"] for s in dash["funnel"]] == [
        "Found", "Saved or prepared", "Applied", "Replied", "Interview", "Offer",
    ]  # fmt: skip
    assert [s["count"] for s in dash["funnel"]] == [3, 3, 2, 1, 1, 0]
    # Both strong matches miss Terraform; Rust too, because the fake AI claimed it as matched
    # but it isn't on the resume, so scoring moved it to missing.
    top = {(g["skill"], g["jobs"]) for g in dash["missing_skills"][:2]}
    assert top == {("Terraform", 2), ("Rust", 2)}
    this_week = dash["weekly"][-1]
    assert this_week["applied"] == 2 and this_week["interviews"] == 1
    assert len(dash["weekly"]) == 8
