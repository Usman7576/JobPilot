"""Every LLM call goes through here: free-tier request limits, schema validation with one
corrective retry, and a usage ledger row per call. Synchronous (used by Celery workers)."""

from __future__ import annotations

import uuid
from collections.abc import Callable
from datetime import UTC, datetime
from decimal import Decimal
from functools import lru_cache

from pydantic import ValidationError
from redis import Redis
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.logging import get_logger
from app.models import UsageEvent
from app.models.enums import UsageFeature
from app.prompts.registry import RenderedPrompt
from app.providers.llm import (
    LLMInvalidOutput,
    LLMQuotaExhausted,
    LLMRateLimited,
    LLMResult,
    get_llm,
)

log = get_logger(__name__)


@lru_cache
def _redis() -> Redis:
    return Redis.from_url(get_settings().redis_url)


def reserve_request() -> None:
    """Count one request against the provider's per-minute and per-day limits.

    Free-tier quotas belong to the API key (the whole app), so the counters are global.
    """
    settings = get_settings()
    now = datetime.now(UTC)
    redis = _redis()
    if settings.llm_rpd:
        day_key = f"llm:rpd:{now:%Y%m%d}"
        used_today = redis.incr(day_key)
        redis.expire(day_key, 172_800)
        if int(used_today) > settings.llm_rpd:  # type: ignore[arg-type]
            raise LLMQuotaExhausted("The AI's free daily request quota is used up")
    if settings.llm_rpm:
        minute_key = f"llm:rpm:{now:%Y%m%d%H%M}"
        used_minute = redis.incr(minute_key)
        redis.expire(minute_key, 120)
        if int(used_minute) > settings.llm_rpm:  # type: ignore[arg-type]
            raise LLMRateLimited("Too many AI requests this minute")


def requests_left_today() -> int | None:
    """Free-tier requests left today on this app's key (None when there's no daily limit)."""
    settings = get_settings()
    if not settings.llm_rpd:
        return None
    used = _redis().get(f"llm:rpd:{datetime.now(UTC):%Y%m%d}")
    return max(0, settings.llm_rpd - int(used or 0))  # type: ignore[arg-type]


def generate[T](
    session: Session,
    *,
    user_id: uuid.UUID | None,
    feature: UsageFeature,
    prompt: RenderedPrompt,
    parse: Callable[[dict[str, object]], T],
    ref_type: str | None = None,
    ref_id: uuid.UUID | None = None,
) -> tuple[T, LLMResult]:
    """Call the LLM and parse its JSON with `parse` (e.g. a Pydantic model_validate).

    On a validation error the model gets one retry with the error described.
    """
    if prompt.spec.schema is None:
        raise ValueError(f"prompt {prompt.spec.ref} has no JSON schema")
    llm = get_llm(prompt.spec.role)
    hint: str | None = None
    for attempt in range(2):
        reserve_request()
        try:
            result = llm.generate_json(
                prompt, schema=prompt.spec.schema, tier=prompt.spec.model_tier, retry_hint=hint
            )
        except LLMInvalidOutput as exc:
            if attempt == 1:
                raise
            hint = str(exc)
            continue
        _record(session, user_id, feature, result, ref_type, ref_id)
        try:
            return parse(result.data), result
        except ValidationError as exc:
            if attempt == 1:
                raise LLMInvalidOutput("model output did not match the schema") from exc
            hint = "; ".join(
                f"{'.'.join(str(p) for p in e['loc'])}: {e['msg']}" for e in exc.errors()[:10]
            )
            log.info("llm_output_retry", prompt=prompt.spec.ref, errors=len(exc.errors()))
    raise LLMInvalidOutput("unreachable")  # pragma: no cover


def _record(
    session: Session,
    user_id: uuid.UUID | None,
    feature: UsageFeature,
    result: LLMResult,
    ref_type: str | None,
    ref_id: uuid.UUID | None,
) -> None:
    session.add(
        UsageEvent(
            user_id=user_id,
            feature=feature,
            provider=result.provider,
            model=result.model,
            input_tokens=result.input_tokens,
            output_tokens=result.output_tokens,
            # Free tiers cost nothing; per-model prices arrive with cost tracking (phase 8).
            cost_usd=Decimal(0),
            ref_type=ref_type,
            ref_id=ref_id,
        )
    )
    session.flush()
