"""Any OpenAI-compatible chat API: Groq (free tier) and Ollama (local, free) both speak it."""

from __future__ import annotations

import json
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


class _Transient(Exception):
    pass


class OpenAICompatibleProvider:
    def __init__(
        self,
        *,
        name: str,
        base_url: str,
        api_key: str,
        smart_model: str,
        fast_model: str,
        require_key: bool = True,
    ) -> None:
        if require_key and not api_key:
            raise LLMNotConfigured(f"No API key configured for {name}")
        self.name = name
        self._base_url = base_url.rstrip("/")
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
        messages = [
            {"role": "system", "content": prompt.system},
            {"role": "user", "content": prompt.user},
        ]
        if retry_hint:
            messages.append(
                {"role": "user", "content": f"Your previous answer was rejected: {retry_hint}"}
            )
        body = {
            "model": model,
            "messages": messages,
            "temperature": prompt.spec.temperature,
            "max_tokens": prompt.spec.max_tokens,
            "response_format": {
                "type": "json_schema",
                "json_schema": {"name": prompt.spec.id, "schema": schema, "strict": False},
            },
        }
        payload = self._post(body)
        try:
            content = payload["choices"][0]["message"]["content"]
            data = json.loads(content)
        except (KeyError, IndexError, TypeError, json.JSONDecodeError) as exc:
            raise LLMInvalidOutput("model returned malformed JSON") from exc
        if not isinstance(data, dict):
            raise LLMInvalidOutput("model returned JSON that is not an object")
        usage = payload.get("usage") or {}
        return LLMResult(
            data=data,
            provider=self.name,
            model=model,
            input_tokens=int(usage.get("prompt_tokens", 0)),
            output_tokens=int(usage.get("completion_tokens", 0)),
        )

    @retry(
        retry=retry_if_exception_type(_Transient),
        stop=stop_after_attempt(3),
        wait=wait_exponential_jitter(initial=2, max=20),
        reraise=True,
    )
    def _post_with_retry(self, body: dict[str, Any]) -> httpx.Response:
        headers = {"Authorization": f"Bearer {self._api_key}"} if self._api_key else {}
        try:
            resp = httpx.post(
                f"{self._base_url}/chat/completions", json=body, headers=headers, timeout=120
            )
        except httpx.TransportError as exc:
            raise _Transient(str(exc)) from exc
        if resp.status_code >= 500:
            raise _Transient(f"HTTP {resp.status_code}")
        return resp

    def _post(self, body: dict[str, Any]) -> dict[str, Any]:
        try:
            resp = self._post_with_retry(body)
        except _Transient as exc:
            raise LLMUnavailable(f"{self.name} is unavailable right now") from exc
        if resp.status_code == 429:
            raise LLMRateLimited(f"{self.name} rate limit reached")
        if resp.status_code in (401, 403):
            raise LLMNotConfigured(f"{self.name} rejected the API key")
        if resp.status_code != 200:
            raise LLMError(f"{self.name} request failed ({resp.status_code})")
        result: dict[str, Any] = resp.json()
        return result
