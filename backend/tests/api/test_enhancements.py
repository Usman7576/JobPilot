from __future__ import annotations

import uuid
from collections.abc import Iterator
from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Job, Resume
from app.models.constants import EMBEDDING_DIM
from app.prompts.registry import RenderedPrompt
from app.providers.llm.fake import FakeLLM
from app.providers.sources import set_sources_override
from app.providers.sources.http import _redis
from tests.api.test_applications import Writer, prepare, setup
from tests.conftest import FakeMailer, csrf_headers, signed_in
from tests.fakes import FakeSource, raw_job


class PrepWriter(Writer):
    """Also answers the interview prep prompt."""

    def __call__(self, prompt: RenderedPrompt) -> dict[str, Any]:
        if prompt.spec.id == "interview_prep":
            assert "<fact_sheet>" in prompt.user and "Python Developer" in prompt.user
            return {
                "questions": [
                    {
                        "question": "Tell us about a service you scaled.",
                        "why": "The role runs high-traffic APIs.",
                        "your_angle": "Your FastAPI services handling 2M requests per day (b1).",
                        "fact_ref": "b1",
                    }
                ],
                "focus_topics": ["PostgreSQL indexing", " "],
                "to_ask": ["How is on-call shared across the team?"],
            }
        return super().__call__(prompt)


@pytest.fixture
def writer(fake_llm: FakeLLM) -> PrepWriter:
    w = PrepWriter()
    fake_llm.responder = w
    return w


@pytest.fixture
def two_roles() -> Iterator[FakeSource]:
    """Two openings at the same company."""
    fake = FakeSource(
        "alpha",
        [
            raw_job("alpha", 1, title="Python Developer", company="Acme Inc"),
            raw_job("alpha", 2, title="Data Engineer", company="Acme Inc"),
        ],
    )
    set_sources_override([fake])
    r = _redis()
    if keys := r.keys("source:*"):
        r.delete(*keys)
    yield fake
    set_sources_override(None)


async def test_answer_bank_is_saved_encrypted(
    client: AsyncClient, mailer: FakeMailer, db: AsyncSession
) -> None:
    await signed_in(client, mailer)
    assert (await client.get("/api/v1/users/me/answers")).json() == {"items": []}
    items = [
        {"question": "Notice period", "answer": "  Two weeks  "},
        {"question": "Expected salary", "answer": "PKR 300,000 a month"},
    ]
    r = await client.put(
        "/api/v1/users/me/answers", json={"items": items}, headers=csrf_headers(client)
    )
    assert r.status_code == 200
    assert r.json()["items"][0] == {"question": "Notice period", "answer": "Two weeks"}
    assert (await client.get("/api/v1/users/me/answers")).json()["items"][1]["answer"] == (
        "PKR 300,000 a month"
    )
    raw = await db.scalar(text("select answer_bank from users where email = 'ada@example.com'"))
    assert raw and b"300,000" not in bytes(raw)  # encrypted at rest

    too_many = [{"question": f"Q{i}", "answer": "A"} for i in range(51)]
    r = await client.put(
        "/api/v1/users/me/answers", json={"items": too_many}, headers=csrf_headers(client)
    )
    assert r.status_code == 422


async def test_same_company_history_and_interview_prep(
    client: AsyncClient, mailer: FakeMailer, fake_llm: FakeLLM, writer: PrepWriter,
    two_roles: FakeSource,
) -> None:  # fmt: skip
    await setup(client, mailer, fake_llm)
    jobs = (await client.get("/api/v1/jobs")).json()["items"]
    by_title = {j["title"]: j["id"] for j in jobs}
    first = await prepare(client, by_title["Python Developer 1"], kinds=["email"])
    assert first["company_history"] == []
    h = csrf_headers(client)
    await client.post(
        f"/api/v1/applications/{first['id']}/mark-applied", json={"channel": "email"}, headers=h
    )
    second = await prepare(client, by_title["Data Engineer 2"], kinds=["email"])
    [seen] = second["company_history"]
    assert seen["id"] == first["id"] and seen["status"] == "applied"
    assert seen["job_title"] == "Python Developer 1"

    r = await client.post(f"/api/v1/applications/{first['id']}/interview-prep", headers=h)
    assert r.status_code == 202
    app = (await client.get(f"/api/v1/applications/{first['id']}")).json()
    prep = app["interview_prep"]["content"]
    assert prep["questions"][0]["your_angle"] == (
        "Your FastAPI services handling 2M requests per day."
    )  # fact ids stripped
    assert prep["focus_topics"] == ["PostgreSQL indexing"]
    assert prep["to_ask"] == ["How is on-call shared across the team?"]
    assert "interview_prep" not in app["versions"]
    assert app["status"] == "applied"  # a prep pack never moves the card


async def test_writes_from_the_closest_named_resume(
    client: AsyncClient, mailer: FakeMailer, fake_llm: FakeLLM, writer: PrepWriter,
    two_roles: FakeSource, db: AsyncSession,
) -> None:  # fmt: skip
    await setup(client, mailer, fake_llm)
    jobs = (await client.get("/api/v1/jobs")).json()["items"]
    job_id = next(j["id"] for j in jobs if j["title"] == "Python Developer 1")
    job = await db.get(Job, uuid.UUID(job_id))
    active = await db.scalar(select(Resume).where(Resume.is_active.is_(True)))
    assert job is not None and active is not None

    def variant(label: str | None, version: int) -> Resume:
        return Resume(
            user_id=active.user_id, version=version, label=label, is_active=False,
            status=active.status, file_key=active.file_key, file_name=active.file_name,
            mime_type=active.mime_type, file_sha256=f"{active.file_sha256}-{version}",
            profile=active.profile, skills_index=active.skills_index,
            embedding=list(job.embedding),  # as close to the job as it gets
        )  # fmt: skip

    away = [0.0] * EMBEDDING_DIM
    away[0] = 1.0
    active.embedding = away
    old = variant(None, 7)  # an unnamed old version is never used, however close
    db.add(old)
    await db.commit()
    unnamed = await prepare(client, job_id, kinds=["email"])
    assert unnamed["resume_id"] == str(active.id) and unnamed["resume_label"] is None

    named = variant("Backend", 8)
    db.add(named)
    await db.commit()
    other_id = next(j["id"] for j in jobs if j["title"] == "Data Engineer 2")
    other_job = await db.get(Job, uuid.UUID(other_id))
    assert other_job is not None
    named.embedding = list(other_job.embedding)
    await db.commit()
    picked = await prepare(client, other_id, kinds=["email"])
    assert picked["resume_id"] == str(named.id) and picked["resume_label"] == "Backend"
