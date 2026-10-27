from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import httpx
import pytest
from google.genai import errors

from app.prompts.registry import load_prompt, render
from app.providers.llm import LLMError
from app.providers.llm import gemini as gemini_module
from app.providers.llm.gemini import GeminiProvider


class _Models:
    def __init__(self, busy: set[str], slow: set[str]) -> None:
        self.busy = busy
        self.slow = slow
        self.calls: list[str] = []

    def generate_content(self, *, model: str, contents: str, config: Any) -> Any:
        self.calls.append(model)
        if model in self.busy:
            raise errors.ServerError(503, {"error": {"message": "high demand"}})
        if model in self.slow:
            raise httpx.ReadTimeout("timed out")
        usage = SimpleNamespace(prompt_token_count=3, candidates_token_count=2)
        return SimpleNamespace(text='{"ok": true}', usage_metadata=usage)


def _provider(
    busy: set[str] = frozenset(), slow: set[str] = frozenset()
) -> tuple[GeminiProvider, _Models]:
    provider = GeminiProvider("test-key", "smart-model", "fast-model")
    models = _Models(set(busy), set(slow))
    provider._client = SimpleNamespace(models=models)  # type: ignore[assignment]
    return provider, models


def _prompt() -> Any:
    return render(load_prompt("resume_parse", 1), resume_text="Jane Doe")


@pytest.fixture(autouse=True)
def _no_backoff(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        gemini_module.GeminiProvider._call_with_retry.retry, "sleep", lambda _s: None
    )  # type: ignore[attr-defined]


def test_busy_smart_model_falls_back_to_fast_model() -> None:
    provider, models = _provider(busy={"smart-model"})
    result = provider.generate_json(_prompt(), schema={}, tier="smart")
    assert result.model == "fast-model"
    assert result.data == {"ok": True}
    assert models.calls == ["smart-model"] * 3 + ["fast-model"]


def test_both_models_busy_raises_llm_error() -> None:
    provider, _ = _provider(busy={"smart-model", "fast-model"})
    with pytest.raises(LLMError, match="unavailable"):
        provider.generate_json(_prompt(), schema={}, tier="smart")


def test_timed_out_smart_model_falls_back_to_fast_model() -> None:
    provider, models = _provider(slow={"smart-model"})
    result = provider.generate_json(_prompt(), schema={}, tier="smart")
    assert result.model == "fast-model"
    assert models.calls == ["smart-model"] * 3 + ["fast-model"]
