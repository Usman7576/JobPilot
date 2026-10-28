from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import parse_qs, urlparse

import httpx
import pytest
import respx
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import sync_session
from app.integrations.gmail import MESSAGES_URL, READ_SCOPE, SEND_SCOPE
from app.models import Integration, User
from app.models.enums import IntegrationProvider, IntegrationStatus
from app.prompts.registry import RenderedPrompt
from app.providers.llm.fake import FakeLLM
from app.services import reply_service
from tests.api.test_applications import Writer, prepare, setup
from tests.api.test_applications import source as source
from tests.conftest import FakeMailer, csrf_headers


class ReplyWriter(Writer):
    """Classifies replies by keywords in the subject line."""

    def __call__(self, prompt: RenderedPrompt) -> dict[str, Any]:
        if prompt.spec.id == "reply_classify":
            assert "@" not in prompt.user  # contact details are stripped before the AI
            text = prompt.user.lower()
            if "interview" in text:
                return {"label": "interview", "confidence": 0.95}
            if "unfortunately" in text:
                return {"label": "rejection", "confidence": 0.6}  # not sure enough to move
            if "received your application" in text:
                return {"label": "auto_reply", "confidence": 0.99}
            return {"label": "positive", "confidence": 0.9}
        return super().__call__(prompt)


@pytest.fixture
def writer(fake_llm: FakeLLM) -> ReplyWriter:
    w = ReplyWriter()
    fake_llm.responder = w
    return w


class Inbox:
    """A fake Gmail that only answers searches and metadata requests."""

    def __init__(self) -> None:
        self.messages: dict[str, dict[str, Any]] = {}
        self.queries: list[str] = []

    def add(self, mid: str, sender: str, subject: str, snippet: str = "Hi") -> None:
        self.messages[mid] = {
            "id": mid,
            "threadId": f"t-{mid}",
            "snippet": snippet + " Call me at +92 300 1234567 or mail jane@acme.example",
            "internalDate": str(int((datetime.now(UTC) + timedelta(minutes=1)).timestamp() * 1000)),
            "payload": {
                "headers": [
                    {"name": "From", "value": sender},
                    {"name": "Subject", "value": subject},
                ]
            },
        }

    def install(self) -> None:
        def search(request: httpx.Request) -> httpx.Response:
            self.queries.append(request.url.params["q"])
            return httpx.Response(200, json={"messages": [{"id": m} for m in self.messages]})

        respx.get(MESSAGES_URL).mock(side_effect=search)
        respx.get(url__regex=rf"{MESSAGES_URL}/[\w-]+").mock(
            side_effect=lambda r: httpx.Response(
                200, json=self.messages[r.url.path.rsplit("/", 1)[1]]
            )
        )


@pytest.fixture
def inbox() -> Iterator[Inbox]:
    with respx.mock:
        respx.route(host="localhost").pass_through()
        box = Inbox()
        box.install()
        yield box


async def applied_application(
    client: AsyncClient, mailer: FakeMailer, fake_llm: FakeLLM
) -> dict[str, Any]:
    job_id = await setup(client, mailer, fake_llm)
    app = await prepare(client, job_id, kinds=["email"])  # contact: jobs@acme.example
    r = await client.post(
        f"/api/v1/applications/{app['id']}/mark-applied",
        json={"channel": "email"},
        headers=csrf_headers(client),
    )
    applied: dict[str, Any] = r.json()
    return applied


async def connect_gmail(db: AsyncSession, read: bool = True) -> None:
    user = await db.scalar(select(User).where(User.email == "ada@example.com"))
    assert user is not None
    db.add(
        Integration(
            user_id=user.id,
            provider=IntegrationProvider.GMAIL,
            status=IntegrationStatus.CONNECTED,
            google_email="ada@gmail.example",
            scopes=["openid", SEND_SCOPE, *([READ_SCOPE] if read else [])],
            access_token="tok",
            refresh_token="ref",
            token_expires_at=datetime.now(UTC) + timedelta(hours=1),
        )
    )
    await db.commit()


def run_check() -> reply_service.CheckResult:
    with sync_session() as s:
        user_id = s.scalar(select(User.id).where(User.email == "ada@example.com"))
        assert user_id is not None
        return reply_service.check(s, user_id)


async def status_of(client: AsyncClient, app_id: str) -> dict[str, Any]:
    data: dict[str, Any] = (await client.get(f"/api/v1/applications/{app_id}")).json()
    return data


async def test_interview_reply_moves_the_card_once(
    client: AsyncClient, mailer: FakeMailer, fake_llm: FakeLLM, writer: ReplyWriter,
    source: Any, db: AsyncSession, inbox: Inbox,
) -> None:  # fmt: skip
    app = await applied_application(client, mailer, fake_llm)
    await connect_gmail(db)
    inbox.add("m1", "Jane Recruiter <jobs@acme.example>", "Interview for the Python Developer role")

    result = run_check()
    assert (result.messages, result.moved) == (1, 1)
    # Only senders you applied to are searched: the exact contact and their company domain.
    assert inbox.queries[0].startswith("from:(jobs@acme.example OR acme.example) after:")
    after = await status_of(client, app["id"])
    assert after["status"] == "interview" and after["follow_up_at"] is None
    assert after["events"][0]["actor"] == "gmail"
    notes = (await client.get("/api/v1/notifications")).json()["items"]
    reply = next(n for n in notes if n["kind"] == "reply_detected")
    assert reply["title"] == "Reply from Acme Inc" and "interview" in reply["body"]

    assert run_check().messages == 0  # the same message isn't processed twice


async def test_auto_replies_and_unsure_rejections(
    client: AsyncClient, mailer: FakeMailer, fake_llm: FakeLLM, writer: ReplyWriter,
    source: Any, db: AsyncSession, inbox: Inbox,
) -> None:  # fmt: skip
    app = await applied_application(client, mailer, fake_llm)
    await connect_gmail(db)
    inbox.add("a1", "jobs@acme.example", "We received your application")
    run_check()
    assert (await status_of(client, app["id"]))["status"] == "applied"  # auto-replies don't count

    inbox.add("r1", "jobs@acme.example", "Your application", "Unfortunately we went another way")
    run_check()
    after = await status_of(client, app["id"])
    assert after["status"] == "replied"  # only 0.6 sure it's a rejection: Replied, not Rejected


async def test_same_company_other_sender_is_only_a_suggestion(
    client: AsyncClient, mailer: FakeMailer, fake_llm: FakeLLM, writer: ReplyWriter,
    source: Any, db: AsyncSession, inbox: Inbox,
) -> None:  # fmt: skip
    app = await applied_application(client, mailer, fake_llm)
    await connect_gmail(db)
    inbox.add("s1", "hr-team@acme.example", "Interview availability")
    result = run_check()
    assert (result.moved, result.suggested) == (0, 1)
    assert (await status_of(client, app["id"]))["status"] == "applied"
    notes = (await client.get("/api/v1/notifications")).json()["items"]
    assert any(n["title"] == "Possible reply from Acme Inc" for n in notes)


async def test_off_without_read_access_and_reauth_on_403(
    client: AsyncClient, mailer: FakeMailer, fake_llm: FakeLLM, writer: ReplyWriter,
    source: Any, db: AsyncSession, inbox: Inbox,
) -> None:  # fmt: skip
    await applied_application(client, mailer, fake_llm)
    await connect_gmail(db, read=False)
    assert run_check().messages == 0 and inbox.queries == []  # never reads without permission
    r = await client.put(
        "/api/v1/integrations/gmail/reply-detection", json={"enabled": True},
        headers=csrf_headers(client),
    )  # fmt: skip
    assert r.status_code == 409 and r.json()["code"] == "needs_read_access"

    await db.execute(
        Integration.__table__.update().values(scopes=["openid", SEND_SCOPE, READ_SCOPE])
    )
    await db.commit()
    status = (await client.get("/api/v1/integrations")).json()["gmail"]
    assert status["can_read"] and status["reply_detection"]
    off = await client.put(
        "/api/v1/integrations/gmail/reply-detection", json={"enabled": False},
        headers=csrf_headers(client),
    )  # fmt: skip
    assert off.json()["gmail"]["reply_detection"] is False
    assert run_check().messages == 0

    await client.put(
        "/api/v1/integrations/gmail/reply-detection", json={"enabled": True},
        headers=csrf_headers(client),
    )  # fmt: skip
    respx.get(MESSAGES_URL).mock(return_value=httpx.Response(403))
    run_check()
    assert (await client.get("/api/v1/integrations")).json()["gmail"]["status"] == "needs_reauth"


async def test_connect_link_asks_for_read_only_access(
    client: AsyncClient, mailer: FakeMailer
) -> None:
    from tests.conftest import signed_in

    await signed_in(client, mailer)
    plain = (await client.get("/api/v1/integrations/gmail/connect")).json()["url"]
    with_read = (await client.get("/api/v1/integrations/gmail/connect?read=true")).json()["url"]
    assert READ_SCOPE not in parse_qs(urlparse(plain).query)["scope"][0]
    assert READ_SCOPE in parse_qs(urlparse(with_read).query)["scope"][0]
