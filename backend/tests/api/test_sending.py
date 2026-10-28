from __future__ import annotations

import base64
import email
import json
import re
import uuid
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from email.message import Message
from pathlib import Path
from typing import Any

import httpx
import pytest
import respx
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import sync_session
from app.integrations.gmail import SEND_URL
from app.models import EmailSendLog, Integration, Notification, User
from app.models.enums import IntegrationStatus, SendStatus
from app.providers.llm.fake import FakeLLM
from app.services import send_service
from tests.api.test_applications import Writer, prepare, setup, words
from tests.api.test_applications import source as source
from tests.api.test_applications import writer as writer
from tests.api.test_replies import connect_gmail
from tests.conftest import FakeMailer, csrf_headers


class Outbox:
    """A fake Gmail send endpoint; `status` makes it fail."""

    def __init__(self) -> None:
        self.sent: list[Message] = []
        self.status = 200

    def handle(self, request: httpx.Request) -> httpx.Response:
        if self.status != 200:
            return httpx.Response(self.status, json={"error": "nope"})
        raw = base64.urlsafe_b64decode(json.loads(request.content)["raw"])
        self.sent.append(email.message_from_bytes(raw))
        return httpx.Response(200, json={"id": f"m{len(self.sent)}", "threadId": "t1"})


@pytest.fixture
def outbox() -> Iterator[Outbox]:
    with respx.mock:
        respx.route(host="localhost").pass_through()
        box = Outbox()
        respx.post(SEND_URL).mock(side_effect=box.handle)
        yield box


@pytest.fixture(autouse=True)
def gmail_backend(monkeypatch: pytest.MonkeyPatch) -> None:
    """Your .env may say smtp (local test mode); these tests are about Gmail."""
    monkeypatch.setattr(send_service.integration_service, "send_backend", lambda: "gmail")


@pytest.fixture
def queued(monkeypatch: pytest.MonkeyPatch) -> list[tuple[uuid.UUID, str, datetime]]:
    """Captures scheduled sends instead of running them, so tests drive the worker."""
    calls: list[tuple[uuid.UUID, str, datetime]] = []
    monkeypatch.setattr(send_service, "_enqueue", lambda *a: calls.append(a))
    return calls


async def ready_application(
    client: AsyncClient, mailer: FakeMailer, fake_llm: FakeLLM, db: AsyncSession
) -> dict[str, Any]:
    job_id = await setup(client, mailer, fake_llm)
    app = await prepare(client, job_id, kinds=["email"])  # contact: jobs@acme.example
    await connect_gmail(db, read=False)
    return app


async def send(
    client: AsyncClient, app_id: str, key: str = "key-12345678", confirmed: bool = True
) -> httpx.Response:
    return await client.post(
        f"/api/v1/applications/{app_id}/send",
        json={"preview_confirmed": confirmed},
        headers={**csrf_headers(client), "Idempotency-Key": key},
    )


def deliver(app_id: str, attempt: int = 1) -> str:
    with sync_session() as s:
        return send_service.deliver(s, uuid.UUID(app_id), attempt)


async def test_send_needs_preview_gmail_and_contact(
    client: AsyncClient, mailer: FakeMailer, fake_llm: FakeLLM, writer: Writer,
    source: Any, db: AsyncSession, queued: list[Any],
) -> None:  # fmt: skip
    job_id = await setup(client, mailer, fake_llm)
    app = await prepare(client, job_id, kinds=["email"])
    r = await send(client, app["id"], confirmed=False)
    assert r.status_code == 422 and r.json()["code"] == "send_not_allowed"
    r = await send(client, app["id"])
    assert r.status_code == 409 and r.json()["code"] == "gmail_not_connected"
    r = await client.post(
        f"/api/v1/applications/{app['id']}/send",
        json={"preview_confirmed": True},
        headers=csrf_headers(client),
    )
    assert r.status_code == 422  # no Idempotency-Key header
    await connect_gmail(db, read=False)
    await client.patch(
        f"/api/v1/applications/{app['id']}", json={"clear_contact": True},
        headers=csrf_headers(client),
    )  # fmt: skip
    r = await send(client, app["id"])
    assert r.status_code == 422 and "address" in r.json()["detail"]
    assert queued == []


async def test_queue_cancel_and_send(
    client: AsyncClient, mailer: FakeMailer, fake_llm: FakeLLM, writer: Writer,
    source: Any, db: AsyncSession, queued: list[Any], outbox: Outbox,
) -> None:  # fmt: skip
    app = await ready_application(client, mailer, fake_llm, db)
    before = datetime.now(UTC)
    r = await send(client, app["id"])
    assert r.status_code == 202, r.text
    body = r.json()
    assert body["status"] == "queued"
    at = datetime.fromisoformat(body["scheduled_send_at"])
    assert before + timedelta(seconds=29) <= at <= before + timedelta(seconds=125)
    assert len(queued) == 1 and queued[0][2] == at

    # A retried click with the same key is answered, not queued twice.
    again = await send(client, app["id"])
    assert again.status_code == 202 and len(queued) == 1
    other = await send(client, app["id"], key="another-key-123")
    assert other.status_code == 409

    quota = (await client.get("/api/v1/applications/send-quota")).json()
    assert quota == {"cap": 25, "sent_today": 0, "queued": 1, "remaining": 24}

    # Nothing can change it while it waits.
    h = csrf_headers(client)
    edit = await client.patch(f"/api/v1/applications/{app['id']}", json={"notes": "x"}, headers=h)
    assert edit.status_code == 409
    move = await client.post(
        f"/api/v1/applications/{app['id']}/move", json={"column": "saved"}, headers=h
    )
    assert move.status_code == 409

    r = await client.post(f"/api/v1/applications/{app['id']}/cancel-send", headers=h)
    assert r.status_code == 200 and r.json()["status"] == "ready"
    assert r.json()["scheduled_send_at"] is None
    assert deliver(app["id"]) == "skipped"  # the revoked task finds nothing to do
    assert outbox.sent == []
    r = await client.post(f"/api/v1/applications/{app['id']}/cancel-send", headers=h)
    assert r.status_code == 409

    # Send for real this time.
    r = await send(client, app["id"], key="second-try-1234")
    assert r.status_code == 202
    assert deliver(app["id"]) == "sent"
    assert len(outbox.sent) == 1
    msg = outbox.sent[0]
    assert msg["To"] == "jobs@acme.example"
    assert msg["Subject"] == body["email"]["content"]["subject"]
    parts = list(msg.walk())
    text = next(p for p in parts if p.get_content_type() == "text/plain")
    assert "Analytical Engines" in text.get_payload(decode=True).decode()
    attachment = next(p for p in parts if p.get_filename())
    assert re.fullmatch(r"\w+_Resume\.pdf", attachment.get_filename() or "")
    assert attachment.get_payload(decode=True).startswith(b"%PDF")

    done = (await client.get(f"/api/v1/applications/{app['id']}")).json()
    assert done["status"] == "applied" and done["channel"] == "email"
    assert done["sent_at"] and done["follow_up_at"]
    assert done["events"][0]["reason"] == "Sent to jobs@acme.example"
    logs = (await db.scalars(select(EmailSendLog))).all()
    assert [entry.status for entry in logs] == [SendStatus.SENT]
    assert deliver(app["id"]) == "skipped"  # a duplicate task never sends twice
    assert (await send(client, app["id"], key="third-try-12345")).status_code == 409
    cancel = await client.post(f"/api/v1/applications/{app['id']}/cancel-send", headers=h)
    assert cancel.status_code == 409 and "already been sent" in cancel.json()["detail"]


async def test_daily_cap(
    client: AsyncClient, mailer: FakeMailer, fake_llm: FakeLLM, writer: Writer,
    source: Any, db: AsyncSession, queued: list[Any], outbox: Outbox,
) -> None:  # fmt: skip
    app = await ready_application(client, mailer, fake_llm, db)
    user = await db.scalar(select(User).where(User.email == "ada@example.com"))
    assert user is not None
    user.daily_send_cap = 1
    db.add(EmailSendLog(user_id=user.id, status=SendStatus.SENT,
                        sent_on=send_service.local_day(user)))  # fmt: skip
    await db.commit()
    r = await send(client, app["id"])
    assert r.status_code == 429 and r.json()["code"] == "daily_send_cap"

    # Checked again at send time (e.g. the cap was lowered after queueing).
    user.daily_send_cap = 2
    await db.commit()
    assert (await send(client, app["id"])).status_code == 202
    user.daily_send_cap = 1
    await db.commit()
    assert deliver(app["id"]) == "failed"
    assert outbox.sent == []
    out = (await client.get(f"/api/v1/applications/{app['id']}")).json()
    assert out["status"] == "ready" and "limit" in out["last_error"]


async def test_gmail_errors(
    client: AsyncClient, mailer: FakeMailer, fake_llm: FakeLLM, writer: Writer,
    source: Any, db: AsyncSession, queued: list[Any], outbox: Outbox,
) -> None:  # fmt: skip
    app = await ready_application(client, mailer, fake_llm, db)

    # Busy: retried, then given up after the last attempt.
    outbox.status = 503
    assert (await send(client, app["id"])).status_code == 202
    assert deliver(app["id"], attempt=1) == "retry"
    out = (await client.get(f"/api/v1/applications/{app['id']}")).json()
    assert out["status"] == "queued"
    assert deliver(app["id"], attempt=send_service.MAX_ATTEMPTS) == "failed"
    out = (await client.get(f"/api/v1/applications/{app['id']}")).json()
    assert out["status"] == "ready" and "busy" in out["last_error"]

    # Permission gone: Gmail needs reconnecting and the user is told.
    outbox.status = 403
    assert (await send(client, app["id"], key="retry-after-busy")).status_code == 202
    assert deliver(app["id"]) == "failed"
    db.expire_all()
    row = await db.scalar(select(Integration))
    assert row is not None and row.status == IntegrationStatus.NEEDS_REAUTH
    notes = (await db.scalars(select(Notification))).all()
    assert any(n.title == "Email not sent" for n in notes)
    r = await send(client, app["id"], key="after-reauth-123")
    assert r.status_code == 409 and r.json()["code"] == "gmail_not_connected"
    assert outbox.sent == []
    logs = (await db.scalars(select(EmailSendLog))).all()
    assert {entry.status for entry in logs} == {SendStatus.FAILED}


async def test_blocked_flags_must_be_confirmed(
    client: AsyncClient, mailer: FakeMailer, fake_llm: FakeLLM, writer: Writer,
    source: Any, db: AsyncSession, queued: list[Any],
) -> None:  # fmt: skip
    writer.email_body = "I know Rust well. " + words(70)
    app = await ready_application(client, mailer, fake_llm, db)
    assert app["flags_blocked"]
    r = await send(client, app["id"])
    assert r.status_code == 409 and r.json()["code"] == "flags_not_acknowledged"
    await client.post(
        f"/api/v1/applications/{app['id']}/acknowledge-flags", headers=csrf_headers(client)
    )
    assert (await send(client, app["id"])).status_code == 202


def test_only_the_send_task_sends_email() -> None:
    """Human in the loop: Gmail's send call is used in exactly one place."""
    root = Path(__file__).resolve().parents[2] / "app"
    callers = sorted(
        str(p.relative_to(root)).replace("\\", "/")
        for p in root.rglob("*.py")
        if "send_raw(" in p.read_text(encoding="utf-8")
    )
    assert callers == ["integrations/gmail.py", "services/send_service.py"]
    tasks = root / "tasks"
    users = [p.name for p in tasks.glob("*.py") if "deliver(" in p.read_text(encoding="utf-8")]
    assert users == ["email_tasks.py"]


async def test_smtp_test_mode_needs_no_gmail(
    client: AsyncClient, mailer: FakeMailer, fake_llm: FakeLLM, writer: Writer,
    source: Any, queued: list[Any], monkeypatch: pytest.MonkeyPatch,
) -> None:  # fmt: skip
    monkeypatch.setattr(send_service.integration_service, "send_backend", lambda: "smtp")
    delivered: list[Message] = []

    class FakeSMTP:
        def __init__(self, host: str, port: int, timeout: int) -> None:
            pass

        def __enter__(self) -> FakeSMTP:
            return self

        def __exit__(self, *exc: object) -> None:
            pass

        def send_message(self, msg: Message) -> None:
            delivered.append(msg)

    monkeypatch.setattr(send_service.smtplib, "SMTP", FakeSMTP)
    job_id = await setup(client, mailer, fake_llm)
    app = await prepare(client, job_id, kinds=["email"])
    assert (await send(client, app["id"])).status_code == 202
    assert deliver(app["id"]) == "sent"
    assert delivered[0]["To"] == "jobs@acme.example"
