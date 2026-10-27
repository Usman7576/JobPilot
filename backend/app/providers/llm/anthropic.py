"""Claude via the Anthropic Messages API (paid; optional writing model).

JSON output uses a forced tool call: the response schema is the tool's input schema, so
the model must answer with one `respond` tool call whose input is our JSON.
"""

from __future__ import annotations

from typing import Any

import httpx
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential_jitter

from app.prompts.registry import ModelTier, RenderedPrompt
from app.providers.llm.base import (
    LLMError,
    LLMInvalidOutput,
    LLMNotConfigured,
    LLMRateLimited,
    LLMResult,
    LLMUnavailable,
)

API_URL = "https://api.anthropic.com/v1/messages"
API_VERSION = "2023-06-01"
TOOL = "respond"


class _Transient(Exception):
    pass


class AnthropicProvider:
    name = "anthropic"

    def __init__(self, api_key: str, smart_model: str, fast_model: str) -> None:
        if not api_key:
            raise LLMNotConfigured("ANTHROPIC_API_KEY is not set")
        self._api_key = api_key
        self._models: dict[ModelTier, str] = {"smart": smart_model, "fast": fast_model}

    def generate_json(
        self,
        prompt: RenderedPrompt,
        *,
        schema: dict[str, Any],
        tier: ModelTier,
        retry_hint: str | None = None,
    ) -> LLMResult:
        model = self._models[tier]
        user = prompt.user
        if retry_hint:
            user += f"\n\nYour previous answer was rejected: {retry_hint}\nAnswer again."
        body = {
            "model": model,
            "system": prompt.system,
            "messages": [{"role": "user", "content": user}],
            "max_tokens": prompt.spec.max_tokens,
            "temperature": prompt.spec.temperature,
            "tools": [
                {
                    "name": TOOL,
                    "description": "Return the answer as structured JSON.",
                    "input_schema": schema,
                }
            ],
            "tool_choice": {"type": "tool", "name": TOOL},
        }
        payload = self._post(body)
        block = next(
            (
                b
                for b in payload.get("content") or []
                if b.get("type") == "tool_use" and b.get("name") == TOOL
            ),
            None,
        )
        if block is None or not isinstance(block.get("input"), dict):
            raise LLMInvalidOutput("Claude didn't return the JSON tool call")
        usage = payload.get("usage") or {}
        return LLMResult(
            data=block["input"],
            provider=self.name,
            model=model,
            input_tokens=int(usage.get("input_tokens", 0)),
            output_tokens=int(usage.get("output_tokens", 0)),
        )

    @retry(
        retry=retry_if_exception_type(_Transient),
        stop=stop_after_attempt(2),
        wait=wait_exponential_jitter(initial=2, max=8),
        reraise=True,
    )
    def _post_with_retry(self, body: dict[str, Any]) -> httpx.Response:
        headers = {"x-api-key": self._api_key, "anthropic-version": API_VERSION}
        try:
            resp = httpx.post(API_URL, json=body, headers=headers, timeout=120)
        except httpx.TimeoutException as exc:
            raise LLMUnavailable("Claude took too long to answer") from exc
        except httpx.TransportError as exc:
            raise _Transient(str(exc)) from exc
        if resp.status_code >= 500:  # includes 529 "overloaded"
            raise _Transient(f"HTTP {resp.status_code}")
        return resp

    def _post(self, body: dict[str, Any]) -> dict[str, Any]:
        try:
            resp = self._post_with_retry(body)
        except _Transient as exc:
            raise LLMUnavailable("Claude is unavailable right now") from exc
        if resp.status_code == 429:
            raise LLMRateLimited("Claude rate limit reached")
        if resp.status_code in (401, 403):
            raise LLMNotConfigured("ANTHROPIC_API_KEY was rejected")
        if resp.status_code != 200:
            raise LLMError(f"Claude request failed ({resp.status_code})")
        result: dict[str, Any] = resp.json()
        return result
