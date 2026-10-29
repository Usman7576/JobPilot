from __future__ import annotations

import dataclasses
import uuid
from collections.abc import Iterator
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.providers.llm.fake import FakeLLM
from app.providers.sources import set_sources_override
from app.providers.sources.http import _redis
from app.services import send_service
from tests.api.test_applications import Writer, setup
from tests.api.test_applications import writer as writer
from tests.api.test_replies import connect_gmail
from tests.conftest import FakeMailer, csrf_headers
from tests.fakes import FakeSource, raw_job


@pytest.fixture
def two_jobs() -> Iterator[FakeSource]:
    """One posting with an email, one without."""
    no_email = dataclasses.replace(
        raw_job("alpha", 2, title="Python Engineer", company="Beta GmbH"),
        description="<p>We use Python and FastAPI. Apply on our careers page.</p>",
    )
    fake = FakeSource(
        "alpha", [raw_job("alpha", 1, title="Python Developer", company="Acme Inc"), no_email]
    )
    set_sources_override([fake])
    r = _redis()
    if keys := r.keys("source:*"):
        r.delete(*keys)
    yield fake
    set_sources_override(None)


@pytest.fixture(autouse=True)
def no_real_sending(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(send_service.integration_service, "send_backend", lambda: "gmail")
    monkeypatch.setattr(send_service, "_enqueue", lambda *a: None)


async def jobs(client: AsyncClient, **params: Any) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = (await client.get("/api/v1/jobs", params=params)).json()["items"]
    return items


async def test_filter_prepare_review_and_send(
    client: AsyncClient, mailer: FakeMailer, fake_llm: FakeLLM, writer: Writer,
    two_jobs: FakeSource, db: AsyncSession,
) -> None:  # fmt: skip
    await setup(client, mailer, fake_llm)
    all_jobs = await jobs(client)
    assert len(all_jobs) == 2 and all(j["application"] is None for j in all_jobs)
    with_email = await jobs(client, has_email="true")
    assert [j["company_name"] for j in with_email] == ["Acme Inc"]
    no_email = next(j for j in all_jobs if j["company_name"] == "Beta GmbH")

    h = csrf_headers(client)
    ghost = str(uuid.uuid4())
    r = await client.post(
        "/api/v1/applications/prepare-batch",
        json={"job_ids": [with_email[0]["id"], no_email["id"], ghost], "tone": "friendly"},
        headers=h,
    )
    assert r.status_code == 202, r.text
    batch = r.json()
    assert len(batch["started"]) == 1
    reasons = {s["job_id"]: s["reason"] for s in batch["skipped"]}
    assert reasons == {no_email["id"]: "No email in the posting", ghost: "Job not found"}

    # Written (inline in tests) and waiting for review; nothing was sent.
    queue = (await client.get("/api/v1/applications/review-queue")).json()
    assert queue["writing"] == 0
    [item] = queue["items"]
    assert item["status"] == "ready" and item["contact_email"] == "jobs@acme.example"
    assert item["email"]["content"]["subject"] and item["tone"] == "friendly"
    assert item["cover_letter"] is None  # an email application needs only the email

    again = await client.post(
        "/api/v1/applications/prepare-batch", json={"job_ids": [with_email[0]["id"]]}, headers=h
    )
    assert again.json()["started"] == []
    assert "in the queue" in again.json()["skipped"][0]["reason"]

    # Approving one in the queue is a normal, confirmed send.
    await connect_gmail(db, read=False)
    r = await client.post(
        f"/api/v1/applications/{item['id']}/send",
        json={"preview_confirmed": True},
        headers={**h, "Idempotency-Key": "review-12345678"},
    )
    assert r.status_code == 202 and r.json()["status"] == "queued"
    assert (await client.get("/api/v1/applications/review-queue")).json()["items"] == []

    marked = await jobs(client, has_email="true")
    assert marked[0]["application"]["status"] == "queued"
    assert await jobs(client, has_email="true", hide_applied="true") == []

    applied = await client.post(
        "/api/v1/applications/prepare-batch", json={"job_ids": [with_email[0]["id"]]}, headers=h
    )
    assert applied.json()["started"] == [] and applied.json()["skipped"][0]["reason"]


async def test_batch_limits(client: AsyncClient, mailer: FakeMailer, fake_llm: FakeLLM) -> None:
    from tests.conftest import signed_in

    await signed_in(client, mailer)
    h = csrf_headers(client)
    too_many = [str(uuid.uuid4()) for _ in range(26)]
    r = await client.post(
        "/api/v1/applications/prepare-batch", json={"job_ids": too_many}, headers=h
    )
    assert r.status_code == 422
    r = await client.post(
        "/api/v1/applications/prepare-batch", json={"job_ids": too_many[:1]}, headers=h
    )
    assert r.status_code == 422 and r.json()["code"] == "no_active_resume"
