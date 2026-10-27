from __future__ import annotations

from app.core.config import get_settings
from app.providers.llm.base import (
    LLMError,
    LLMInvalidOutput,
    LLMNotConfigured,
    LLMProvider,
    LLMQuotaExhausted,
    LLMRateLimited,
    LLMResult,
    LLMUnavailable,
)

_override: LLMProvider | None = None
_instance: LLMProvider | None = None


def set_llm_override(provider: LLMProvider | None) -> None:
    """Tests swap in FakeLLM."""
    global _override
    _override = provider


def get_llm() -> LLMProvider:
    """Build the configured provider once. Raises LLMNotConfigured if keys are missing."""
    global _instance
    if _override is not None:
        return _override
    if _instance is None:
        _instance = _build()
    return _instance


def _build() -> LLMProvider:
    s = get_settings()
    if s.llm_provider == "gemini":
        from app.providers.llm.gemini import GeminiProvider

        return GeminiProvider(s.gemini_api_key, s.gemini_model, s.gemini_fast_model)
    if s.llm_provider in ("groq", "ollama"):
        from app.providers.llm.openai_compat import OpenAICompatibleProvider

        if s.llm_provider == "groq":
            return OpenAICompatibleProvider(
                name="groq",
                base_url=s.groq_base_url,
                api_key=s.groq_api_key,
                smart_model=s.groq_model,
                fast_model=s.groq_fast_model,
            )
        return OpenAICompatibleProvider(
            name="ollama",
            base_url=s.ollama_base_url,
            api_key="",
            smart_model=s.ollama_model,
            fast_model=s.ollama_model,
            require_key=False,
        )
    raise LLMNotConfigured(f"LLM_PROVIDER={s.llm_provider} has no real implementation")


__all__ = [
    "LLMError",
    "LLMInvalidOutput",
    "LLMNotConfigured",
    "LLMProvider",
    "LLMQuotaExhausted",
    "LLMRateLimited",
    "LLMResult",
    "LLMUnavailable",
    "get_llm",
    "set_llm_override",
]
