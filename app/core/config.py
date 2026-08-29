"""Application settings, loaded from the environment (never hardcoded)."""
from __future__ import annotations

from functools import lru_cache

from pydantic import Field, PostgresDsn
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Every knob the service needs, validated at import time."""

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    # --- Application ---
    APP_NAME: str = "PDD API"
    API_V1_PREFIX: str = "/api/v1"
    DEBUG: bool = False
    CORS_ORIGINS: list[str] = Field(default_factory=lambda: ["http://localhost:5173"])

    # --- Database (async DSN, asyncpg driver) ---
    DATABASE_URL: PostgresDsn

    # --- Security ---
    SECRET_KEY: str = Field(min_length=32)
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 12
    REFRESH_TOKEN_EXPIRE_DAYS: int = 30

    # --- Bootstrap admin, created by scripts/create_admin.py ---
    ADMIN_IIN: str | None = None
    ADMIN_PASSWORD: str | None = None
    ADMIN_NAME: str = "Admin"
    ADMIN_SURNAME: str = "Root"

    # --- Media ---
    MEDIA_SERVE_LOCAL: bool = True
    MEDIA_ROOT: str = "../media_store"
    MEDIA_URL_PREFIX: str = "/media"
    MEDIA_ORIGIN_OTAN: str = "https://otan-shymkent.kz"
    MEDIA_ORIGIN_PDDTEST: str = "https://media.pddtest.kz"


@lru_cache
def get_settings() -> Settings:
    return Settings() 
