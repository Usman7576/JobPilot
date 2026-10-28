from __future__ import annotations

import io
import json
import zipfile
from datetime import UTC, datetime, timedelta

import httpx
import respx
from httpx import AsyncClient
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.integrations.google_oauth import REVOKE_URL
from app.models import Integration, Job, Resume, User
from app.models.enums import IntegrationProvider, IntegrationStatus
from app.providers.llm.fake import FakeLLM
from app.providers.storage import LocalStorage
from tests.api.test_matching import score_by_title, setup_user, source  # noqa: F401
from tests.conftest import FakeMailer, csrf_headers
from tests.fakes import FakeSource


async def connect_google(db: AsyncSession) -> None:
    user = await db.scalar(select(User).where(User.email == "ada@example.com"))
    assert user is not None
    db.add(
        Integration(
            user_id=user.id,
            provider=IntegrationProvider.GMAIL,
            status=IntegrationStatus.CONNECTED,
            google_email="ada@gmail.example",
            access_token="secret-access",
            refresh_token="secret-refresh",
            token_expires_at=datetime.now(UTC) + timedelta(hours=1),
        )
    )
    await db.commit()


async def test_export_has_your_data_and_no_secrets(
    client: AsyncClient,
    mailer: FakeMailer,
    fake_llm: FakeLLM,
    source: FakeSource,  # noqa: F811
    db: AsyncSession,
) -> None:
    await setup_user(client, mailer, fake_llm)
    fake_llm.responder = score_by_title
    await client.post("/api/v1/searches", headers=csrf_headers(client))
    job_id = (await client.get("/api/v1/jobs")).json()["items"][0]["id"]
    await client.post(f"/api/v1/jobs/{job_id}/save", headers=csrf_headers(client))
    await connect_google(db)

    r = await client.get("/api/v1/users/me/export")
    assert r.status_code == 200 and r.headers["content-type"] == "application/zip"
    zf = zipfile.ZipFile(io.BytesIO(r.content))
    names = set(zf.namelist())
    assert {"account.json", "resumes.json", "jobs.json", "matches.json", "applications.json",
            "connected_accounts.json", "README.txt"} <= names  # fmt: skip
    assert any(n.startswith("resumes/v1_") for n in names)  # the original file, decrypted
    assert json.loads(zf.read("account.json"))["email"] == "ada@example.com"
    assert json.loads(zf.read("resumes.json"))[0]["profile"]["name"] == "Ada Lovelace"
    assert len(json.loads(zf.read("applications.json"))) == 1
    everything = b"".join(zf.read(n) for n in names if n.endswith(".json"))
    for secret in (b"password_hash", b"secret-access", b"secret-refresh", b'"embedding":'):
        assert secret not in everything


@respx.mock
async def test_deleting_the_account_removes_everything(
    client: AsyncClient,
    mailer: FakeMailer,
    fake_llm: FakeLLM,
    source: FakeSource,  # noqa: F811
    db: AsyncSession,
    storage: LocalStorage,
) -> None:
    respx.route(host="localhost").pass_through()
    revoke = respx.post(REVOKE_URL).mock(return_value=httpx.Response(200))
    await setup_user(client, mailer, fake_llm)
    fake_llm.responder = score_by_title
    await client.post("/api/v1/searches", headers=csrf_headers(client))
    job_id = (await client.get("/api/v1/jobs")).json()["items"][0]["id"]
    await client.post(f"/api/v1/jobs/{job_id}/save", headers=csrf_headers(client))
    await connect_google(db)
    user = await db.scalar(select(User).where(User.email == "ada@example.com"))
    assert user is not None
    user_id = user.id
    keys = list(await db.scalars(select(Resume.file_key).where(Resume.user_id == user_id)))
    assert keys and all(storage.get(k) for k in keys)

    r = await client.request(
        "DELETE", "/api/v1/users/me", json={"confirm": "delete"}, headers=csrf_headers(client)
    )
    assert r.status_code == 422 and r.json()["code"] == "confirmation_mismatch"

    r = await client.request(
        "DELETE", "/api/v1/users/me", json={"confirm": "DELETE"}, headers=csrf_headers(client)
    )
    assert r.status_code == 204
    assert revoke.called  # Google access revoked, not just forgotten
    assert (await client.get("/api/v1/users/me")).status_code == 401

    db.expire_all()
    # Every table with a user_id column has nothing left for this user.
    tables = (
        await db.execute(
            text(
                "select table_name from information_schema.columns "
                "where column_name = 'user_id' and table_schema = 'public'"
            )
        )
    ).scalars()
    for table in tables:
        left = await db.scalar(
            text(f'select count(*) from "{table}" where user_id = :u'),  # noqa: S608
            {"u": user_id},
        )
        assert left == 0, table
    assert await db.get(User, user_id) is None
    for key in keys:  # the encrypted resume files are gone from storage too
        try:
            storage.get(key)
            raise AssertionError("file still stored")
        except FileNotFoundError:
            pass
    # Shared job postings stay: they aren't personal data.
    assert (await db.scalar(select(func.count()).select_from(Job))) >= 1

    r = await client.post(
        "/api/v1/auth/login",
        json={"email": "ada@example.com", "password": "correct horse battery"},
        headers=csrf_headers(client),
    )
    assert r.status_code == 401  # the account is gone
