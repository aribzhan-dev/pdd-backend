"""HTTP hardening applied to every response the API returns.

These headers defend the JSON API and the media it serves: nosniff stops a
browser second-guessing a content type, DENY forbids framing the responses,
and a strict referrer policy keeps tokens out of outbound Referer headers.
The single-page app itself is served by nginx, which sets the same headers
for the HTML and static assets (see DEPLOY.md).

HSTS is opt-in: it only makes sense over HTTPS, so it is gated on a setting
rather than sent unconditionally, which would wrongly pin a plain-HTTP dev
host in the browser for a year.
"""
from __future__ import annotations

from collections.abc import Awaitable, Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

#: Static headers sent on every response, independent of transport.
_BASE_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Cross-Origin-Opener-Policy": "same-origin",
    "Permissions-Policy": "geolocation=(), microphone=(), camera=()",
}

#: One year, the value browsers expect before honouring HSTS preloading.
_HSTS_VALUE = "max-age=31536000; includeSubDomains"


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Attach hardening headers to each response."""

    def __init__(self, app: Callable, *, enable_hsts: bool = False) -> None:
        super().__init__(app)
        self._enable_hsts = enable_hsts

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        response = await call_next(request)
        for header, value in _BASE_HEADERS.items():
            response.headers.setdefault(header, value)
        if self._enable_hsts:
            response.headers.setdefault("Strict-Transport-Security", _HSTS_VALUE)
        return response
