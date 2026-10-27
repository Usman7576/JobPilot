from __future__ import annotations

from app.core.config import get_settings
from app.prompts.registry import PromptRole
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
_instances: dict[str, LLMProvider] = {}


def set_llm_override(provider: LLMProvider | None) -> None:
    """Tests swap in FakeLLM (for every role)."""
    global _override
    _override = provider


def get_llm(role: PromptRole = "default") -> LLMProvider:
    """The configured provider for a prompt role, built once.

    "writing" prompts (emails, cover letters) use WRITING_LLM_PROVIDER when it's set, so a
    stronger writer can be paid for while everything else stays on the free tier.
    Raises LLMNotConfigured if keys are missing.
    """
    if _override is not None:
        return _override
    s = get_settings()
    name = (s.writing_llm_provider if role == "writing" else "") or s.llm_provider
    if name not in _instances:
        _instances[name] = _build(name)
    return _instances[name]


def _build(name: str) -> LLMProvider:
    s = get_settings()
    if name == "gemini":
        from app.providers.llm.gemini import GeminiProvider

        return GeminiProvider(s.gemini_api_key, s.gemini_model, s.gemini_fast_model)
    if name == "anthropic":
        from app.providers.llm.anthropic import AnthropicProvider

        return AnthropicProvider(s.anthropic_api_key, s.anthropic_model, s.anthropic_fast_model)
    if name in ("groq", "ollama"):
        from app.providers.llm.openai_compat import OpenAICompatibleProvider

        if name == "groq":
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
    raise LLMNotConfigured(f"LLM provider {name!r} has no real implementation")


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
