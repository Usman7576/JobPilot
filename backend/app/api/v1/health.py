from __future__ import annotations

from fastapi import APIRouter, Response
from redis.asyncio import Redis
from sqlalchemy import text

from app.core.config import get_settings
from app.core.deps import DbSession
from app.schemas.common import ApiModel

router = APIRouter(prefix="/health", tags=["health"])


class HealthOut(ApiModel):
    status: str
    checks: dict[str, str] = {}


@router.get("/live")
async def live() -> HealthOut:
    return HealthOut(status="ok")


@router.get("/ready", responses={503: {"model": HealthOut}})
async def ready(db: DbSession, response: Response) -> HealthOut:
    checks: dict[str, str] = {}
    try:
        await db.execute(text("SELECT 1"))
        checks["database"] = "ok"
    except Exception:
        checks["database"] = "error"
    try:
        redis = Redis.from_url(get_settings().redis_url, socket_timeout=2)
        await redis.ping()
        await redis.aclose()
        checks["redis"] = "ok"
    except Exception:
        checks["redis"] = "error"

    healthy = all(v == "ok" for v in checks.values())
    if not healthy:
        response.status_code = 503
    return HealthOut(status="ok" if healthy else "degraded", checks=checks)
