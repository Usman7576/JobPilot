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
    password_hash_memory_kib: int = 65_536
    google_client_id: str = ""
    google_client_secret: str = ""

    # --- Sending defaults ---
    default_daily_send_cap: int = 25
    max_daily_send_cap: int = 50
    default_follow_up_days: int = 7
    # Each send waits a random 30-120 s (cancellable) and sends are >= 30 s apart per user.
    send_delay_min_seconds: int = 30
    send_delay_max_seconds: int = 120
    send_spacing_seconds: int = 30
    # gmail: the user's connected Gmail. smtp: local testing only, delivers through SMTP_URL
    # (Mailpit in dev) and is refused in production.
    application_send_backend: Literal["gmail", "smtp"] = "gmail"
    # Optional: finds recruiter emails when a posting has none (free plan: 25 searches/month).
    hunter_api_key: str = ""

    # --- AI ---
    default_monthly_ai_budget_usd: float = 0.0
    llm_provider: Literal["gemini", "groq", "ollama", "fake"] = "gemini"
    # Optional separate model for writing (emails, cover letters); empty = same as above.
    writing_llm_provider: Literal["", "gemini", "groq", "ollama", "anthropic", "fake"] = ""
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-sonnet-5-5"
    anthropic_fast_model: str = "claude-haiku-5-5"
    gemini_api_key: str = ""
    # "-latest" aliases follow Google's newest Flash models, so free-tier model
    # retirements don't break the app. Pin exact ids here if you need stability.
    gemini_model: str = "gemini-flash-latest"
    gemini_fast_model: str = "gemini-flash-lite-latest"
    groq_api_key: str = ""
    groq_base_url: str = "https://api.groq.com/openai/v1"
    # Groq's free tier allows ~8k tokens/minute per model; Llama 3.x models were retired.
    groq_model: str = "openai/gpt-oss-120b"
    groq_fast_model: str = "openai/gpt-oss-20b"
    ollama_base_url: str = "http://host.docker.internal:11434/v1"
    ollama_model: str = "qwen2.5:7b"
    # Free tiers are limited by requests, not dollars. 0 disables the limit.
    llm_rpm: int = 10
    llm_rpd: int = 500
    embedding_provider: Literal["fastembed", "fake"] = "fastembed"
    embedding_model: str = "BAAI/bge-base-en-v1.5"
    model_cache_dir: str = "/data/models"

    # --- Storage / uploads ---
    storage_backend: Literal["local"] = "local"
    local_storage_path: str = "/data/uploads"
    max_upload_mb: int = 5
    max_resume_pages: int = 10

    # --- Job sources ---
    adzuna_app_id: str = ""
    adzuna_app_key: str = ""
    adzuna_default_country: str = "us"
    jooble_api_key: str = ""
    serpapi_key: str = ""
    jobspy_proxies: CsvList = Field(default_factory=list)
    jobspy_fetch_description: bool = False
    jobspy_country_indeed: str = "usa"
    source_max_queries_per_run: int = 6
    source_timeout_seconds: int = 30
    normalize_with_llm: bool = False
    # How many of the best-matching unscored jobs the AI scores per search (5 per request).
    stage1_top_n: int = 15
    job_ttl_days: int = 30

    # --- Celery ---
    celery_task_always_eager: bool = False

    # --- Transactional email ---
    mail_backend: Literal["console", "smtp"] = "console"
    smtp_url: str = "smtp://localhost:1025"
    mail_from: str = "JobPilot AI <noreply@jobpilot.local>"

    # --- Observability ---
    log_level: str = "INFO"
    log_json: bool = False

    @field_validator("encryption_keys", "jobspy_proxies", mode="before")
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
    def google_gmail_redirect_uri(self) -> str:
        return f"{self.app_base_url}/api/v1/integrations/gmail/callback"

    @property
    def google_login_enabled(self) -> bool:
        return bool(self.google_client_id and self.google_client_secret)


@lru_cache
def get_settings() -> Settings:
    return Settings()
