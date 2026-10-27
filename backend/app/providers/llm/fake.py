from __future__ import annotations

from collections import deque
from typing import Any

from app.prompts.registry import ModelTier, RenderedPrompt
from app.providers.llm.base import LLMError, LLMResult


class FakeLLM:
    """Deterministic stand-in for tests: returns queued responses (dicts or exceptions)."""

    name = "fake"

    def __init__(self, responses: list[dict[str, Any] | Exception] | None = None) -> None:
        self.responses: deque[dict[str, Any] | Exception] = deque(responses or [])
        self.calls: list[RenderedPrompt] = []
        self.retry_hints: list[str | None] = []

    def queue(self, *responses: dict[str, Any] | Exception) -> None:
        self.responses.extend(responses)

    def generate_json(
        self,
        prompt: RenderedPrompt,
        *,
        schema: dict[str, Any],
        tier: ModelTier,
        retry_hint: str | None = None,
    ) -> LLMResult:
        self.calls.append(prompt)
        self.retry_hints.append(retry_hint)
        if not self.responses:
            raise LLMError("FakeLLM has no queued response")
        item = self.responses.popleft()
        if isinstance(item, Exception):
            raise item
        return LLMResult(
            data=item, provider="fake", model=f"fake-{tier}", input_tokens=100, output_tokens=50
        )
