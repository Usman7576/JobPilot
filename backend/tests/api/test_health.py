from __future__ import annotations

from httpx import AsyncClient


async def test_live(client: AsyncClient) -> None:
    r = await client.get("/api/v1/health/live")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"
    assert r.headers["x-request-id"]


async def test_ready_checks_database_and_redis(client: AsyncClient) -> None:
    r = await client.get("/api/v1/health/ready")
    assert r.status_code == 200, r.text
    assert r.json()["checks"] == {"database": "ok", "redis": "ok"}


async def test_openapi_has_stable_operation_ids(client: AsyncClient) -> None:
    spec = (await client.get("/api/v1/openapi.json")).json()
    ops = {op["operationId"] for path in spec["paths"].values() for op in path.values()}
    assert {"auth_login", "auth_signup", "users_get_me", "health_live"} <= ops
