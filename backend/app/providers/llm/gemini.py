from __future__ import annotations

import json
from typing import Any

import httpx
from google import genai
from google.genai import errors, types
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential_jitter

from app.prompts.registry import ModelTier, RenderedPrompt
from app.providers.llm.base import (
    LLMError,
    LLMInvalidOutput,
    LLMNotConfigured,
    LLMQuotaExhausted,
    LLMRateLimited,
    LLMResult,
    LLMUnavailable,
)

REQUEST_TIMEOUT_MS = 90_000


class _Transient(Exception):
    """A 5xx answer: worth one quick retry on the same model."""


class _Overloaded(LLMUnavailable):
    """The model is overloaded (5xx after a retry) or too slow (timeout)."""


class GeminiProvider:
    name = "gemini"

    def __init__(self, api_key: str, smart_model: str, fast_model: str) -> None:
        if not api_key:
            raise LLMNotConfigured(
                "GEMINI_API_KEY is not set. Create a free key at https://aistudio.google.com/apikey"
            )
        # A request stuck in an overloaded model's queue fails after this and moves to the
        # lighter model instead of holding a worker for minutes.
        self._client = genai.Client(
            api_key=api_key,
            http_options=types.HttpOptions(
                timeout=REQUEST_TIMEOUT_MS,
                # The SDK's own retries (5 attempts, up to 60 s apart) would stack on ours
                # and keep a worker busy for many minutes while Gemini is overloaded.
                retry_options=types.HttpRetryOptions(attempts=1),
            ),
        )
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
            user += f"\n\nYour previous answer was rejected: {retry_hint}\nReturn corrected JSON."
        config = types.GenerateContentConfig(
            system_instruction=prompt.system,
            temperature=prompt.spec.temperature,
            max_output_tokens=prompt.spec.max_tokens,
            response_mime_type="application/json",
            response_json_schema=schema,
        )
        try:
            response = self._call(model, user, config)
        except _Overloaded:
            # Busy models answer 503 for a while; the lighter model usually still has room.
            fallback = self._models["fast"]
            if fallback == model:
                raise
            model = fallback
            response = self._call(model, user, config)

        text = response.text or ""
        try:
            data = json.loads(text)
        except json.JSONDecodeError as exc:
            raise LLMInvalidOutput("model returned malformed JSON") from exc
        if not isinstance(data, dict):
            raise LLMInvalidOutput("model returned JSON that is not an object")

        usage = response.usage_metadata
        return LLMResult(
            data=data,
            provider=self.name,
            model=model,
            input_tokens=(usage.prompt_token_count or 0) if usage else 0,
            output_tokens=(usage.candidates_token_count or 0) if usage else 0,
        )

    @retry(
        retry=retry_if_exception_type(_Transient),
        stop=stop_after_attempt(2),
        wait=wait_exponential_jitter(initial=2, max=8),
        reraise=True,
    )
    def _call_with_retry(
        self, model: str, user: str, config: types.GenerateContentConfig
    ) -> types.GenerateContentResponse:
        try:
            return self._client.models.generate_content(model=model, contents=user, config=config)
        except errors.ServerError as exc:
            raise _Transient(str(exc)) from exc
        except httpx.TimeoutException as exc:
            # Already waited the full timeout: retrying the same model just doubles the wait.
            raise _Overloaded("Gemini took too long to answer") from exc
        except httpx.TransportError as exc:
            raise _Transient(str(exc)) from exc

    def _call(
        self, model: str, user: str, config: types.GenerateContentConfig
    ) -> types.GenerateContentResponse:
        try:
            return self._call_with_retry(model, user, config)
        except _Transient as exc:
            raise _Overloaded("Gemini is unavailable right now") from exc
        except errors.ClientError as exc:
            if exc.code == 429:
                message = str(exc).lower()
                if "per day" in message or "perday" in message or "daily" in message:
                    raise LLMQuotaExhausted("Gemini free-tier daily quota used up") from exc
                raise LLMRateLimited("Gemini rate limit reached") from exc
            if exc.code in (401, 403):
                raise LLMNotConfigured("GEMINI_API_KEY was rejected by Google") from exc
            raise LLMError(f"Gemini request failed ({exc.code})") from exc
