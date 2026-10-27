from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from app.prompts.registry import ModelTier, RenderedPrompt


class LLMError(Exception):
    """The provider failed (network, 5xx, bad response). Safe to retry later."""

    code = "llm_error"


class LLMNotConfigured(LLMError):
    code = "llm_not_configured"


class LLMRateLimited(LLMError):
    """Per-minute limit hit: retry in a minute."""

    code = "llm_rate_limited"


class LLMQuotaExhausted(LLMError):
    """Daily quota used up: retry tomorrow."""

    code = "llm_quota_exhausted"


class LLMInvalidOutput(LLMError):
    code = "llm_invalid_output"


@dataclass(frozen=True)
class LLMResult:
    data: dict[str, Any]
    provider: str
    model: str
    input_tokens: int = 0
    output_tokens: int = 0


class LLMProvider(Protocol):
    name: str

    def generate_json(
        self,
        prompt: RenderedPrompt,
        *,
        schema: dict[str, Any],
        tier: ModelTier,
        retry_hint: str | None = None,
    ) -> LLMResult:
        """Return JSON matching `schema`. `retry_hint` describes why the last answer failed."""
        ...
