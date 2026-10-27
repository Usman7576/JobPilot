"""Shared HTTP helpers for API-based sources: retries on transient errors, clear failures."""

from __future__ import annotations

import json
from functools import lru_cache
from typing import Any, cast

import httpx
from redis import Redis
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential_jitter

from app.core.config import get_settings
from app.providers.sources.base import SourceError

USER_AGENT = "JobPilotAI/0.1 (personal job search assistant)"


class _Transient(Exception):
    pass


@retry(
    retry=retry_if_exception_type(_Transient),
    stop=stop_after_attempt(3),
    wait=wait_exponential_jitter(initial=2, max=20),
    reraise=True,
)
def _request(method: str, url: str, **kwargs: Any) -> httpx.Response:
    headers = {"User-Agent": USER_AGENT, "Accept": "application/json", **kwargs.pop("headers", {})}
    try:
        resp = httpx.request(
            method, url, headers=headers, timeout=get_settings().source_timeout_seconds, **kwargs
        )
    except httpx.TransportError as exc:
        raise _Transient(str(exc)) from exc
    if resp.status_code >= 500:
        raise _Transient(f"HTTP {resp.status_code}")
    return resp


def request_json(method: str, url: str, **kwargs: Any) -> Any:
    try:
        resp = _request(method, url, **kwargs)
    except _Transient as exc:
        raise SourceError("unavailable", "The source didn't respond. Try again later.") from exc
    if resp.status_code == 429:
        raise SourceError("rate_limited", "The source is rate-limiting us. Try again later.")
    if resp.status_code in (401, 403):
        raise SourceError("auth_failed", "The source rejected the API key.")
    if resp.status_code != 200:
        raise SourceError("http_error", f"The source returned HTTP {resp.status_code}.")
    try:
        return resp.json()
    except ValueError as exc:
        raise SourceError("bad_response", "The source returned something unreadable.") from exc


@lru_cache
def _redis() -> Redis:
    return Redis.from_url(get_settings().redis_url)


def cached_json(key: str, ttl_seconds: int, loader: Any) -> Any:
    """Share one fetch across all users for feeds that ask to be called rarely."""
    redis = _redis()
    hit = redis.get(f"source-cache:{key}")
    if hit is not None:
        return json.loads(cast(bytes, hit))
    data = loader()
    redis.set(f"source-cache:{key}", json.dumps(data), ex=ttl_seconds)
    return data
