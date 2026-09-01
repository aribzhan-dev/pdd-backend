"""Translate domain errors into HTTP responses with a stable shape."""
from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.core.exceptions import AppError


def register_error_handlers(app: FastAPI) -> None:
    """Attach the handler that renders AppError subclasses."""

    @app.exception_handler(AppError)
    async def handle_app_error(_: Request, exc: AppError) -> JSONResponse:
        """Every expected failure answers with the same JSON envelope."""
        # A rate-limit lock advertises how long to wait, per RFC 7231.
        retry_after = getattr(exc, "retry_after", None)
        headers = {"Retry-After": str(retry_after)} if retry_after else None
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "success": False,
                "data": None,
                "error": exc.message,
            },
            headers=headers,
        )
