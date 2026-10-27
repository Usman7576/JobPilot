from __future__ import annotations

import uuid
from pathlib import Path

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import sync_session
from app.models import UsageEvent
from app.providers.llm import LLMQuotaExhausted, LLMRateLimited
from app.providers.llm.fake import FakeLLM
from app.providers.storage import LocalStorage
from app.services import resume_pipeline
from tests.conftest import FakeMailer, csrf_headers, signed_in
from tests.fixtures import make_docx, make_pdf, parsed_resume_json

DOCX = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"


async def upload(client: AsyncClient, data: bytes, name: str = "resume.pdf") -> dict:  # type: ignore[type-arg]
    r = await client.post(
        "/api/v1/resumes",
        files={"file": (name, data, "application/octet-stream")},
        headers=csrf_headers(client),
    )
    return {**r.json(), "http": r.status_code}


async def test_upload_parses_and_activates(
    client: AsyncClient, mailer: FakeMailer, fake_llm: FakeLLM, db: AsyncSession
) -> None:
    await signed_in(client, mailer)
    fake_llm.queue(parsed_resume_json())

    body = await upload(client, make_pdf(), "Ada Lovelace CV.pdf")
    assert body["http"] == 202
    # Tasks run inline in tests, so parsing has finished by the time we read it back.
    r = await client.get(f"/api/v1/resumes/{body['id']}")
    resume = r.json()
    assert resume["status"] == "parsed", resume
    assert resume["version"] == 1
    assert resume["is_active"] is True
    assert resume["file_name"] == "Ada Lovelace CV.pdf"
    assert resume["has_embedding"] is True
    assert resume["seniority"] == "senior"
    skills = [s["name"] for s in resume["profile"]["skills"]]
    assert skills.count("Python") == 1 and "Kubernetes" in skills
    # The resume text actually reached the prompt as tagged data.
    assert "Analytical Engines Ltd" in fake_llm.calls[0].user

    me = (await client.get("/api/v1/users/me")).json()
    assert me["onboarding_step"] == "profile"
    assert await db.scalar(select(func.count()).select_from(UsageEvent)) == 1


async def test_file_is_encrypted_at_rest_and_downloads_intact(
    client: AsyncClient, mailer: FakeMailer, fake_llm: FakeLLM, storage: LocalStorage
) -> None:
    await signed_in(client, mailer)
    fake_llm.queue(parsed_resume_json())
    original = make_docx()
    body = await upload(client, original, "cv.docx")

    stored = list(Path(storage._root).rglob("*.bin"))
    assert len(stored) == 1
    assert b"Ada Lovelace" not in stored[0].read_bytes()
    assert not stored[0].read_bytes().startswith(b"PK")

    r = await client.get(f"/api/v1/resumes/{body['id']}/file")
    assert r.status_code == 200
    assert r.content == original
    assert r.headers["content-type"] == DOCX
    assert "cv.docx" in r.headers["content-disposition"]


async def test_rejects_bad_files(client: AsyncClient, mailer: FakeMailer) -> None:
    await signed_in(client, mailer)
    for data, fragment in [
        (b"<html>not a resume</html>", "PDF and DOCX"),
        (b"", "empty"),
        (make_pdf([["page"]] * 11), "at most 10 pages"),
    ]:
        body = await upload(client, data)
        assert body["http"] == 422, body
        assert body["code"] == "invalid_upload"
        assert fragment in body["detail"]


async def test_duplicate_upload_conflicts(
    client: AsyncClient, mailer: FakeMailer, fake_llm: FakeLLM
) -> None:
    await signed_in(client, mailer)
    fake_llm.queue(parsed_resume_json())
    pdf = make_pdf()
    assert (await upload(client, pdf))["http"] == 202
    body = await upload(client, pdf)
    assert body["http"] == 409
    assert "version 1" in body["detail"]


async def test_missing_api_key_fails_with_helpful_message(
    client: AsyncClient, mailer: FakeMailer
) -> None:
    # No fake_llm fixture: the configured provider ("fake") has no real implementation.
    await signed_in(client, mailer)
    body = await upload(client, make_pdf())
    resume = (await client.get(f"/api/v1/resumes/{body['id']}")).json()
    assert resume["status"] == "failed"
    assert resume["error_code"] == "llm_not_configured"
    assert "GEMINI_API_KEY" in resume["error_message"]
    assert resume["is_active"] is False


async def test_quota_exhausted_then_reparse_succeeds(
    client: AsyncClient, mailer: FakeMailer, fake_llm: FakeLLM
) -> None:
    await signed_in(client, mailer)
    fake_llm.queue(LLMQuotaExhausted("daily"))
    body = await upload(client, make_pdf())
    resume = (await client.get(f"/api/v1/resumes/{body['id']}")).json()
    assert resume["error_code"] == "llm_quota_exhausted"

    fake_llm.queue(parsed_resume_json())
    r = await client.post(f"/api/v1/resumes/{body['id']}/reparse", headers=csrf_headers(client))
    assert r.status_code == 202
    resume = (await client.get(f"/api/v1/resumes/{body['id']}")).json()
    assert resume["status"] == "parsed"
    assert resume["error_code"] is None


async def test_rate_limit_leaves_resume_waiting_for_retry(
    client: AsyncClient, mailer: FakeMailer, fake_llm: FakeLLM
) -> None:
    await signed_in(client, mailer)
    fake_llm.queue(LLMQuotaExhausted("daily"))
    rid = uuid.UUID((await upload(client, make_pdf()))["id"])

    # The task layer retries rate limits; the pipeline must leave the resume retryable.
    fake_llm.queue(LLMRateLimited("busy"))
    with sync_session() as session, pytest.raises(LLMRateLimited):
        resume_pipeline.parse_resume(session, rid)
    resume = (await client.get(f"/api/v1/resumes/{rid}")).json()
    assert resume["status"] == "uploaded"
    assert resume["error_code"] is None

    # After the last retry the task gives up with a clear message.
    with sync_session() as session:
        resume_pipeline.mark_failed(session, rid, "llm_rate_limited", "Try later.")
    resume = (await client.get(f"/api/v1/resumes/{rid}")).json()
    assert resume["status"] == "failed"
    assert resume["error_code"] == "llm_rate_limited"


async def test_profile_edit_bumps_version_and_reembeds(
    client: AsyncClient, mailer: FakeMailer, fake_llm: FakeLLM
) -> None:
    await signed_in(client, mailer)
    fake_llm.queue(parsed_resume_json())
    rid = (await upload(client, make_pdf()))["id"]
    profile = (await client.get(f"/api/v1/resumes/{rid}")).json()["profile"]

    profile["skills"].append({"name": "golang", "category": "language", "proficiency": "beginner"})
    profile["summary"] = "Edited summary."
    r = await client.put(
        f"/api/v1/resumes/{rid}/profile", json=profile, headers=csrf_headers(client)
    )
    assert r.status_code == 200, r.text
    updated = r.json()
    assert updated["profile_version"] == 2
    assert updated["has_embedding"] is True
    assert "Go" in [s["name"] for s in updated["profile"]["skills"]]
    assert updated["profile"]["summary"] == "Edited summary."
    me = (await client.get("/api/v1/users/me")).json()
    assert me["onboarding_step"] == "preferences"

    bad = {**profile, "skills": [{"name": ""}]}
    r = await client.put(f"/api/v1/resumes/{rid}/profile", json=bad, headers=csrf_headers(client))
    assert r.status_code == 422


async def test_versions_activate_and_delete(
    client: AsyncClient, mailer: FakeMailer, fake_llm: FakeLLM
) -> None:
    await signed_in(client, mailer)
    fake_llm.queue(parsed_resume_json(), parsed_resume_json(name="Ada L."))
    first = (await upload(client, make_pdf()))["id"]
    second = (await upload(client, make_docx()))["id"]

    listed = (await client.get("/api/v1/resumes")).json()
    assert [r["version"] for r in listed] == [2, 1]
    assert [r["is_active"] for r in listed] == [True, False]
    active = (await client.get("/api/v1/resumes/active")).json()
    assert active["id"] == second and active["profile"]["name"] == "Ada L."

    r = await client.post(f"/api/v1/resumes/{first}/activate", headers=csrf_headers(client))
    assert r.json()["is_active"] is True
    assert (await client.get("/api/v1/resumes/active")).json()["id"] == first

    r = await client.delete(f"/api/v1/resumes/{first}", headers=csrf_headers(client))
    assert r.status_code == 204
    # The newest remaining parsed version takes over.
    assert (await client.get("/api/v1/resumes/active")).json()["id"] == second


async def test_other_users_cannot_see_my_resume(
    client: AsyncClient, mailer: FakeMailer, fake_llm: FakeLLM
) -> None:
    await signed_in(client, mailer)
    fake_llm.queue(parsed_resume_json())
    rid = (await upload(client, make_pdf()))["id"]

    await client.post("/api/v1/auth/logout", headers=csrf_headers(client))
    await signed_in(client, mailer, email="eve@example.com")
    for method, path in [
        ("GET", f"/api/v1/resumes/{rid}"),
        ("GET", f"/api/v1/resumes/{rid}/file"),
        ("POST", f"/api/v1/resumes/{rid}/activate"),
        ("DELETE", f"/api/v1/resumes/{rid}"),
    ]:
        r = await client.request(method, path, headers=csrf_headers(client))
        assert r.status_code == 404, (method, path)
    assert (await client.get("/api/v1/resumes")).json() == []
