from __future__ import annotations

import base64
from typing import Any

import pytest
from pydantic import ValidationError

from app.core.config import Settings

SAFE: dict[str, Any] = {
    "env": "production",
    "app_base_url": "https://jobpilot.example.com",
    "secret_key": "s" * 40,
    "encryption_keys": base64.urlsafe_b64encode(b"k" * 32).decode(),
    "file_master_key": base64.b64encode(b"m" * 32).decode(),
    "database_url": "postgresql+psycopg://u:p@db/jobpilot",
    "application_send_backend": "gmail",
    "mail_backend": "smtp",
    "llm_provider": "gemini",
    "writing_llm_provider": "",
    "rate_limit_enabled": True,
    "require_email_verification": True,
}


def make(**overrides: Any) -> Settings:
    return Settings(_env_file=None, **{**SAFE, **overrides})  # type: ignore[call-arg]


def test_safe_production_settings_start() -> None:
    assert make().is_production and make().cookie_secure


@pytest.mark.parametrize(
    ("override", "message"),
    [
        ({"app_base_url": "http://jobpilot.example.com"}, "https://"),
        ({"application_send_backend": "smtp"}, "local testing only"),
        ({"mail_backend": "console"}, "MAIL_BACKEND"),
        ({"file_master_key": ""}, "FILE_MASTER_KEY"),
        ({"rate_limit_enabled": False}, "RATE_LIMIT_ENABLED"),
        ({"llm_provider": "fake"}, "fake AI"),
    ],
)
def test_unsafe_production_settings_refuse_to_start(override: dict[str, Any], message: str) -> None:
    with pytest.raises(ValidationError, match=message):
        make(**override)


def test_development_allows_local_shortcuts() -> None:
    dev = make(env="development", app_base_url="http://localhost:3000", mail_backend="console")
    assert not dev.is_production
