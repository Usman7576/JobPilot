from __future__ import annotations

from collections import deque
from collections.abc import Callable
from typing import Any

from app.prompts.registry import ModelTier, RenderedPrompt
from app.providers.llm.base import LLMError, LLMResult

Responder = Callable[[RenderedPrompt], dict[str, Any]]
FakeResponse = dict[str, Any] | Exception | Responder


class FakeLLM:
    """Deterministic stand-in for tests: returns queued responses (dicts or exceptions), or
    calls a queued function with the prompt to build the answer."""

    name = "fake"

    def __init__(self, responses: list[FakeResponse] | None = None) -> None:
        self.responses: deque[FakeResponse] = deque(responses or [])
        self.responder: Responder | None = None  # answers when the queue is empty
        self.calls: list[RenderedPrompt] = []
        self.retry_hints: list[str | None] = []

    def queue(self, *responses: FakeResponse) -> None:
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
        if self.responses:
            item = self.responses.popleft()
        elif self.responder is not None:
            item = self.responder
        else:
            raise LLMError("FakeLLM has no queued response")
        if isinstance(item, Exception):
            raise item
        if callable(item):
            item = item(prompt)
        return LLMResult(
            data=item, provider="fake", model=f"fake-{tier}", input_tokens=100, output_tokens=50
        )
