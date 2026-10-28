from __future__ import annotations

import json
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import parse_qs, urlparse

import httpx
import pytest
import respx
from httpx import AsyncClient
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import sync_session
from app.integrations.google_sheets import API
from app.models import Integration, SearchRun, User
from app.models.enums import IntegrationProvider, IntegrationStatus, SearchTrigger
from app.providers.llm.fake import FakeLLM
from app.providers.sources import set_sources_override
from app.providers.sources.http import _redis
from app.services import schedule_service
from tests.api.test_matching import PREFS, score_by_title, setup_user
from tests.conftest import FakeMailer, csrf_headers, signed_in
from tests.fakes import FakeSource, raw_job

DAILY = {**PREFS, "daily_search_enabled": True, "daily_search_hour": 0, "digest_min_score": 80}


@pytest.fixture
def source() -> Iterator[FakeSource]:
    fake = FakeSource(
        "alpha",
        [
            raw_job("alpha", 1, title="Python Developer", company="Acme Inc"),
            raw_job("alpha", 2, title="Python Intern", company="Intern Co"),
            raw_job("alpha", 3, title="Java Developer", company="Beta GmbH"),
        ],
    )
    set_sources_override([fake])
    r = _redis()
    for pattern in ("source:*", "sheets:*"):
        if keys := r.keys(pattern):
            r.delete(*keys)
    yield fake
    set_sources_override(None)


async def save_prefs(client: AsyncClient, **extra: Any) -> None:
    r = await client.put(
        "/api/v1/preferences", json={**DAILY, **extra}, headers=csrf_headers(client)
    )
    assert r.status_code == 200, r.text


def dispatch(now: datetime | None = None) -> int:
    with sync_session() as session:
        return len(schedule_service.dispatch_due(session, now))


async def scheduled_runs(db: AsyncSession) -> list[SearchRun]:
    rows = await db.scalars(
        select(SearchRun)
        .where(SearchRun.trigger == SearchTrigger.SCHEDULED)
        .order_by(SearchRun.created_at)
    )
    return list(rows)


async def test_daily_search_runs_once_a_day_per_kind(
    client: AsyncClient, mailer: FakeMailer, fake_llm: FakeLLM, source: FakeSource, db: AsyncSession
) -> None:
    await setup_user(client, mailer, fake_llm)
    fake_llm.responder = score_by_title
    await save_prefs(client, daily_search_kinds=["jobs", "internships"])
    prefs = (await client.get("/api/v1/preferences")).json()
    assert prefs["daily_search_kinds"] == ["jobs", "internships"]

    assert dispatch() == 1  # jobs first...
    assert dispatch() == 1  # ...internships on the next tick, once the first is done
    assert dispatch() == 0  # both done today
    kinds = [r.query_snapshot["kind"] for r in await scheduled_runs(db)]
    assert kinds == ["jobs", "internships"]
    assert dispatch(datetime.now(UTC) + timedelta(days=1)) == 1  # tomorrow again


async def test_not_due_before_the_chosen_hour_or_when_off(
    client: AsyncClient, mailer: FakeMailer, fake_llm: FakeLLM, source: FakeSource, db: AsyncSession
) -> None:
    await signed_in(client, mailer)
    await save_prefs(client, daily_search_hour=23, daily_search_enabled=False)
    assert dispatch() == 0
    await save_prefs(client, daily_search_hour=23)
    early = datetime.now(UTC).replace(hour=1, minute=0)
    assert dispatch(early) == 0
    assert dispatch(early.replace(hour=23, minute=30)) == 1


async def test_digest_emails_new_strong_matches(
    client: AsyncClient, mailer: FakeMailer, fake_llm: FakeLLM, source: FakeSource
) -> None:
    await setup_user(client, mailer, fake_llm)
    fake_llm.responder = score_by_title
    await save_prefs(client)
    mailer.sent.clear()
    assert dispatch() == 1

    digest = mailer.sent[-1]
    assert digest.to == "ada@example.com"
    assert digest.subject == "2 new strong job matches for you (score 80+)"  # the Python jobs
    assert "Python Developer 1 at Acme Inc" in digest.text
    assert "Java Developer" not in digest.text  # scored below the 80 threshold
    assert "http://localhost:3000/jobs/" in digest.text and digest.html is not None
    assert "&lt;" not in digest.subject


async def test_no_digest_when_turned_off_or_nothing_new(
    client: AsyncClient, mailer: FakeMailer, fake_llm: FakeLLM, source: FakeSource
) -> None:
    await setup_user(client, mailer, fake_llm)
    fake_llm.responder = score_by_title
    await save_prefs(client, digest_enabled=False)
    mailer.sent.clear()
    dispatch()
    assert mailer.sent == []

    await save_prefs(client)
    dispatch(datetime.now(UTC) + timedelta(days=1))  # same jobs again: nothing new
    assert mailer.sent == []


# --- Google Sheets -------------------------------------------------------------------------


async def connect_sheets(db: AsyncSession, email: str = "ada@example.com") -> None:
    user = await db.scalar(select(User).where(User.email == email))
    assert user is not None
    db.add(
        Integration(
            user_id=user.id,
            provider=IntegrationProvider.SHEETS,
            status=IntegrationStatus.CONNECTED,
            google_email=email,
            access_token="tok",
            refresh_token="ref",
            token_expires_at=datetime.now(UTC) + timedelta(hours=1),
        )
    )
    await db.commit()


@respx.mock
async def test_sheet_is_created_then_rewritten(
    client: AsyncClient, mailer: FakeMailer, fake_llm: FakeLLM, source: FakeSource, db: AsyncSession
) -> None:
    respx.route(host="localhost").pass_through()
    create = respx.post(API).mock(
        return_value=httpx.Response(
            200, json={"spreadsheetId": "s1", "spreadsheetUrl": "https://docs.google.com/s1"}
        )
    )
    clear = respx.post(f"{API}/s1/values:batchClear").mock(
        return_value=httpx.Response(200, json={})
    )
    write = respx.post(f"{API}/s1/values:batchUpdate").mock(
        return_value=httpx.Response(200, json={})
    )
    await setup_user(client, mailer, fake_llm)
    fake_llm.responder = score_by_title
    await client.post("/api/v1/searches", headers=csrf_headers(client))
    await connect_sheets(db)

    r = await client.post("/api/v1/integrations/sheets/sync", headers=csrf_headers(client))
    assert r.status_code == 202
    body = json.loads(create.calls[0].request.content)
    assert body["properties"]["title"] == "JobPilot AI Tracker"
    assert [s["properties"]["title"] for s in body["sheets"]] == ["Jobs", "Applications"]
    assert json.loads(clear.calls[0].request.content) == {"ranges": ["Jobs", "Applications"]}
    data = {d["range"]: d["values"] for d in json.loads(write.calls[0].request.content)["data"]}
    jobs, apps = data["Jobs!A1"], data["Applications!A1"]
    assert jobs[0][:3] == ["job_id", "title", "company"] and len(jobs) == 4
    assert {row[2] for row in jobs[1:]} == {"Acme Inc", "Intern Co", "Beta GmbH"}
    assert apps == [apps[0]]  # header only: nothing applied yet

    status = (await client.get("/api/v1/integrations")).json()["sheets"]
    assert status["spreadsheet_url"] == "https://docs.google.com/s1"
    assert status["last_sync_at"] is not None and status["last_error"] is None

    # Applying queues a sync; the sheet is reused, not created again.
    job_id = (await client.get("/api/v1/jobs")).json()["items"][0]["id"]
    app = (await client.post(f"/api/v1/jobs/{job_id}/save", headers=csrf_headers(client))).json()
    await client.post(
        f"/api/v1/applications/{app['id']}/mark-applied", json={}, headers=csrf_headers(client)
    )
    assert create.call_count == 1
    last = json.loads(write.calls[-1].request.content)["data"]
    app_rows = next(d["values"] for d in last if d["range"] == "Applications!A1")
    assert app_rows[1][5] == "applied"


@respx.mock
async def test_sheet_errors_are_handled(
    client: AsyncClient, mailer: FakeMailer, db: AsyncSession, source: FakeSource
) -> None:
    respx.route(host="localhost").pass_through()
    await signed_in(client, mailer)
    await connect_sheets(db)
    user = await db.scalar(select(User).where(User.email == "ada@example.com"))
    assert user is not None
    await db.execute(
        update(Integration)
        .where(Integration.user_id == user.id)
        .values(config={"spreadsheet_id": "gone", "spreadsheet_url": "x"})
    )
    await db.commit()

    respx.post(f"{API}/gone/values:batchClear").mock(return_value=httpx.Response(404))
    await client.post("/api/v1/integrations/sheets/sync", headers=csrf_headers(client))
    status = (await client.get("/api/v1/integrations")).json()["sheets"]
    assert status["spreadsheet_url"] is None  # a new sheet is made next time
    assert "no longer exists" in status["last_error"]

    respx.post(API).mock(return_value=httpx.Response(401))
    await client.post("/api/v1/integrations/sheets/sync", headers=csrf_headers(client))
    status = (await client.get("/api/v1/integrations")).json()["sheets"]
    assert status["status"] == "needs_reauth"


async def test_sheets_connect_asks_only_for_its_own_files(
    client: AsyncClient, mailer: FakeMailer
) -> None:
    await signed_in(client, mailer)
    url = (await client.get("/api/v1/integrations/sheets/connect")).json()["url"]
    q = parse_qs(urlparse(url).query)
    assert q["scope"] == ["openid email https://www.googleapis.com/auth/drive.file"]
    assert q["redirect_uri"] == ["http://localhost:3000/api/v1/integrations/sheets/callback"]
    # A Gmail state can't be replayed on the Sheets callback.
    await client.get("/api/v1/integrations/gmail/connect")
    r = await client.get("/api/v1/integrations/sheets/callback?code=x&state=y")
    assert r.headers["location"].endswith("/settings?sheets=expired")
    r = await client.post("/api/v1/integrations/sheets/sync", headers=csrf_headers(client))
    assert r.status_code == 409  # not connected
