from __future__ import annotations

from httpx import AsyncClient

from app.providers.llm.fake import FakeLLM
from tests.api.test_matching import score_by_title, setup_user, source  # noqa: F401
from tests.conftest import FakeMailer, csrf_headers, signed_in
from tests.fakes import FakeSource


async def test_usage_counts_this_months_requests(
    client: AsyncClient,
    mailer: FakeMailer,
    fake_llm: FakeLLM,
    source: FakeSource,  # noqa: F811
) -> None:
    await setup_user(client, mailer, fake_llm)  # one resume parse
    fake_llm.responder = score_by_title
    await client.post("/api/v1/searches", headers=csrf_headers(client))  # one scoring batch

    u = (await client.get("/api/v1/usage")).json()
    features = {f["feature"]: f["requests"] for f in u["by_feature"]}
    assert features == {"resume_parse": 1, "score": 1}
    assert u["requests"] == 2 and u["input_tokens"] == 200 and u["output_tokens"] == 100
    assert u["cost_usd"] == 0
    assert u["by_model"][0]["provider"] == "fake"
    assert len(u["daily"]) == 30 and u["daily"][-1]["requests"] == 2
    assert u["provider"] == "fake" and u["writing_provider"] == "fake"
    assert u["requests_left_today"] is None  # no daily limit in tests


async def test_usage_is_private(client: AsyncClient, mailer: FakeMailer) -> None:
    await signed_in(client, mailer, email="new@example.com")
    u = (await client.get("/api/v1/usage")).json()
    assert u["requests"] == 0 and u["by_feature"] == []
