"""Application settings, loaded once at process start.

We use a Pydantic ``BaseSettings`` (rather than reading ``os.environ`` ad-hoc) so that
every config value has a typed schema, a default, and a single source of truth. The
rest of the codebase imports ``get_settings()`` instead of touching env vars directly,
which makes overriding values in tests trivial.
"""

from __future__ import annotations

from enum import StrEnum
from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Environment(StrEnum):
    """Deployment environment. Drives logging format and safety toggles."""

    development = "development"
    staging = "staging"
    production = "production"


class Settings(BaseSettings):
    """Top-level config. One instance per process via :func:`get_settings`.

    Fields map to env vars via the upper-case name (Pydantic's default behaviour).
    Override in tests with ``monkeypatch.setenv`` or by constructing ``Settings(...)``
    directly and injecting the result through dependency overrides.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        # Extra env vars (e.g. POSTGRES_USER used by docker-compose) shouldn't error.
        extra="ignore",
        case_sensitive=False,
    )

    # --- App ---
    environment: Environment = Environment.development
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    api_host: str = "0.0.0.0"
    api_port: int = 8000

    # --- Database ---
    database_url: str = Field(
        default="postgresql+asyncpg://aitrans:devpassword_ganti_apa_aja@localhost:5432/aitrans_db",
        description="SQLAlchemy async URL. Must use the asyncpg driver.",
    )

    # --- Redis ---
    redis_url: str = "redis://localhost:6379/0"

    # --- Anthropic ---
    anthropic_api_key: str = Field(
        default="sk-ant-api03-placeholder",
        description="Replace with a real key in .env. Never commit one.",
    )
    anthropic_model: str = "claude-sonnet-4-6"
    # Lang-detection agents use Haiku (cheap + fast). The main translate
    # stays on Sonnet for translation quality.
    # Short alias (not the date-stamped variant) so it matches the PRICING_TABLE
    # key in src/providers/pricing.py; the Anthropic SDK accepts either form.
    anthropic_haiku_model: str = "claude-haiku-4-5"

    # --- Cache ---
    cache_ttl_seconds: int = 86_400  # 24h, matches the design decision in CLAUDE.md

    # --- Auth (sub-proyek I) ---
    jwt_secret: str = Field(
        default="dev-jwt-secret-replace-in-env-min-32-chars-please",
        min_length=16,
        description="HS256 signing secret. Replace via env var in production.",
    )
    api_key_master: str = Field(
        default="aitkey_master_dev",
        description="Admin / Streamlit master API key (dev only). Bypasses per-tenant auth.",
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Cached accessor. We cache because Settings parses env on construction and
    we want that to happen exactly once per process. Tests that need a fresh
    instance can call ``get_settings.cache_clear()``.
    """
    return Settings()
