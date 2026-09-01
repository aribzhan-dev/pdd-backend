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
    #: Serve /docs, /redoc and /openapi.json. Handy in development and for
    #: handing the API to another developer; off in production by default so
    #: the full API surface is not published to anyone who asks.
    ENABLE_DOCS: bool = False
    CORS_ORIGINS: list[str] = Field(default_factory=lambda: ["http://localhost:5173"])

    # --- Sign-in brute-force guard ---
    #: Failed sign-ins from one IP allowed inside the window before it locks.
    LOGIN_MAX_ATTEMPTS: int = 5
    #: How far back failures are counted, in minutes.
    LOGIN_WINDOW_MINUTES: int = 15
    #: How long a tripped address stays locked, in minutes.
    LOGIN_BLOCK_MINUTES: int = 15
    #: Trust X-Forwarded-For for the client IP. On behind nginx (the real
    #: address is in the header); off when the app is exposed directly, where
    #: the header would be attacker-controlled.
    TRUST_PROXY_HEADERS: bool = True

    # --- HTTP security headers ---
    #: Send Strict-Transport-Security. On in production (HTTPS); leave off for
    #: plain-HTTP local development so the browser does not pin localhost.
    ENABLE_HSTS: bool = False

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
