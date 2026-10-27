from __future__ import annotations

from functools import lru_cache
from typing import Annotated, Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

CsvList = Annotated[list[str], NoDecode]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore", case_sensitive=False)

    # --- Core ---
    env: Literal["development", "test", "production"] = "development"
    app_name: str = "JobPilot AI"
    app_base_url: str = "http://localhost:3000"
    secret_key: str = Field(min_length=32)
    encryption_keys: CsvList = Field(min_length=1)
    file_master_key: str = ""
    require_email_verification: bool = True
    rate_limit_enabled: bool = True

    # --- Database / Redis ---
    database_url: str
    test_database_url: str = ""
    redis_url: str = "redis://localhost:6379/0"
    celery_broker_url: str = "redis://localhost:6379/1"
    celery_result_backend: str = "redis://localhost:6379/2"

    # --- Auth ---
    access_token_ttl_minutes: int = 15
    refresh_token_ttl_days: int = 30
    verification_token_ttl_hours: int = 24
    password_reset_ttl_minutes: int = 60
    google_client_id: str = ""
    google_client_secret: str = ""

    # --- Sending defaults ---
    default_daily_send_cap: int = 25
    max_daily_send_cap: int = 50
    default_follow_up_days: int = 7

    # --- AI defaults ---
    default_monthly_ai_budget_usd: float = 0.0

    # --- Transactional email ---
    mail_backend: Literal["console", "smtp"] = "console"
    smtp_url: str = "smtp://localhost:1025"
    mail_from: str = "JobPilot AI <noreply@jobpilot.local>"

    # --- Observability ---
    log_level: str = "INFO"
    log_json: bool = False

    @field_validator("encryption_keys", mode="before")
    @classmethod
    def _split_keys(cls, v: object) -> object:
        if isinstance(v, str):
            return [k.strip() for k in v.split(",") if k.strip()]
        return v

    @property
    def is_production(self) -> bool:
        return self.env == "production"

    @property
    def cookie_secure(self) -> bool:
        return self.app_base_url.startswith("https://")

    @property
    def google_login_redirect_uri(self) -> str:
        return f"{self.app_base_url}/api/v1/auth/google/callback"

    @property
    def google_login_enabled(self) -> bool:
        return bool(self.google_client_id and self.google_client_secret)


@lru_cache
def get_settings() -> Settings:
    return Settings()
