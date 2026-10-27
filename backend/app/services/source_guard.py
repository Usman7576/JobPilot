"""Politeness and resilience for job sources, shared across workers via Redis.

- Minimum gap between requests to the same provider.
- Circuit breaker: after 3 failed runs in a row a source pauses for an hour.
"""

from __future__ import annotations

import time
from functools import lru_cache
from typing import cast

from redis import Redis

from app.core.config import get_settings
from app.providers.sources import SourceInfo

FAILURES_TO_OPEN = 3
OPEN_SECONDS = 3600
MAX_WAIT_SECONDS = 30.0


@lru_cache
def _redis() -> Redis:
    return Redis.from_url(get_settings().redis_url)


def wait_turn(info: SourceInfo, sleep: bool = True) -> float:
    """Block until this provider may be called again. Returns seconds waited."""
    redis = _redis()
    key = f"source:next:{info.name}"
    now = time.time()
    raw = redis.get(key)
    next_allowed = float(cast(bytes, raw)) if raw else 0.0
    wait = min(max(0.0, next_allowed - now), MAX_WAIT_SECONDS)
    redis.set(key, max(now, next_allowed) + info.min_interval_seconds, ex=3600)
    if wait and sleep:
        time.sleep(wait)
    return wait


def is_paused(name: str) -> bool:
    return bool(_redis().exists(f"source:open:{name}"))


def paused_for(name: str) -> int:
    ttl = int(_redis().ttl(f"source:open:{name}"))  # type: ignore[arg-type]
    return max(ttl, 0)


def record_failure(name: str) -> bool:
    """Returns True if this failure paused the source."""
    redis = _redis()
    key = f"source:fail:{name}"
    failures = int(redis.incr(key))  # type: ignore[arg-type]
    redis.expire(key, OPEN_SECONDS)
    if failures >= FAILURES_TO_OPEN:
        redis.set(f"source:open:{name}", 1, ex=OPEN_SECONDS)
        redis.delete(key)
        return True
    return False


def record_success(name: str) -> None:
    _redis().delete(f"source:fail:{name}")
