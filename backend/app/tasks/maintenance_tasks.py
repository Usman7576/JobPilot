from __future__ import annotations

import time

from redis import Redis

from app.core.config import get_settings
from app.tasks.celery_app import celery_app

HEARTBEAT_KEY = "worker:heartbeat"


@celery_app.task
def ping() -> str:
    return "pong"


@celery_app.task
def heartbeat() -> None:
    """Scheduled by beat; proves beat -> broker -> worker works end to end."""
    redis = Redis.from_url(get_settings().redis_url)
    redis.set(HEARTBEAT_KEY, int(time.time()), ex=300)
