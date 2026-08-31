"""Application entry point: middleware, routers and static media."""
from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api.errors import register_error_handlers
from app.api.v1 import api_router
from app.core.config import get_settings

settings = get_settings()

# The interactive docs describe every endpoint and payload. That is exactly
# what a developer needs and exactly what an attacker would like, so whether
# they exist at all is a deployment setting.
app = FastAPI(
    title=settings.APP_NAME,
    version="1.0.0",
    debug=settings.DEBUG,
    docs_url="/docs" if settings.ENABLE_DOCS else None,
    redoc_url="/redoc" if settings.ENABLE_DOCS else None,
    openapi_url="/openapi.json" if settings.ENABLE_DOCS else None,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

register_error_handlers(app)
app.include_router(api_router, prefix=settings.API_V1_PREFIX)

# The store is mounted only when this deployment serves media itself. In
# production the URLs point at the origin platforms, so there is nothing to
# mount and no 570 MB to keep on the VPS.
_media_root = Path(settings.MEDIA_ROOT)
if settings.MEDIA_SERVE_LOCAL and _media_root.is_dir():
    app.mount(
        settings.MEDIA_URL_PREFIX,
        StaticFiles(directory=_media_root),
        name="media",
    )


@app.get("/health", tags=["system"])
async def health() -> dict[str, str]:
    """Liveness probe."""
    return {"status": "ok", "version": app.version}
