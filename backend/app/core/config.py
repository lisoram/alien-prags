"""Application settings, read from environment variables / .env.

Every config value the backend needs lives here. Nothing else in the app
should read os.environ directly.
"""

from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Look for .env in the current dir and one level up, so it works whether
    # you run from the repo root or from backend/. Real env vars win over .env.
    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"),
        env_file_encoding="utf-8",
        extra="ignore",  # .env also holds compose-only vars like POSTGRES_USER
    )

    DATABASE_URL: str
    QDRANT_URL: str
    QDRANT_API_KEY: str | None = None
    GEMINI_API_KEY: str
    GEMINI_GENERATION_MODEL: str
    GEMINI_EMBEDDING_MODEL: str
    STORAGE_BACKEND: Literal["local"] = "local"
    STORAGE_LOCAL_ROOT: str = "./storage"
    CORS_ORIGINS: str = "http://localhost:3000"  # comma-separated
    LOG_LEVEL: str = "INFO"
    DOMAINS_DIR: str = "../domains"  # folder holding the domain packs (relative to where you run)
    # DEV ONLY. When true, a domain with `enabled: true` is served even though it
    # has no passing eval run. Never set this in production.
    ALLOW_UNEVALUATED_DOMAINS: bool = False

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.CORS_ORIGINS.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
