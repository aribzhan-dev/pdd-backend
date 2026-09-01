"""In-memory brute-force guard for the sign-in endpoint.

A wrong IIN or password may be an honest typo, so a handful of tries is fine;
a flood of them from one address is an attack. This keeps a short-lived count
of recent failures per client IP and locks that address out once it crosses a
threshold, for a fixed cool-off period.

The store lives in the process, not in Redis: the service runs on a single VPS
and the numbers are tiny. With more than one worker each keeps its own tally,
so the effective threshold is (workers x limit) — acceptable here, and the
first line of defence is paired with an nginx `limit_req` rule at deploy time.
Swap this class for a Redis-backed one if the deployment ever grows.

Only *failed* attempts count. A successful login clears the address, so a
student who mistypes twice and then succeeds starts fresh next time.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from functools import lru_cache

from starlette.requests import Request

from app.core.config import get_settings
from app.core.time import utc_now


@dataclass
class _Bucket:
    """Recent failures for one address, plus an optional lock expiry."""

    failures: deque[datetime] = field(default_factory=deque)
    locked_until: datetime | None = None


class LoginRateLimiter:
    """Counts failed sign-ins per IP and locks abusive addresses out.

    Not tied to FastAPI so it can be unit-tested with a plain clock. All state
    is in memory and pruned lazily on access, so it never grows without bound.
    """

    def __init__(self, *, max_attempts: int, window: timedelta, block: timedelta) -> None:
        if max_attempts < 1:
            raise ValueError("max_attempts must be at least 1")
        self._max_attempts = max_attempts
        self._window = window
        self._block = block
        self._buckets: dict[str, _Bucket] = {}

    def retry_after(self, key: str) -> int | None:
        """Seconds until `key` may try again, or None if it is not locked."""
        bucket = self._buckets.get(key)
        if bucket is None or bucket.locked_until is None:
            return None
        remaining = (bucket.locked_until - utc_now()).total_seconds()
        if remaining <= 0:
            # The lock lapsed: forget the address so it starts clean.
            self._buckets.pop(key, None)
            return None
        return int(remaining) + 1

    def record_failure(self, key: str) -> int | None:
        """Register a failed attempt; return the lock's retry-after if it trips."""
        now = utc_now()
        bucket = self._buckets.setdefault(key, _Bucket())
        self._prune(bucket, now)

        bucket.failures.append(now)
        if len(bucket.failures) >= self._max_attempts:
            bucket.locked_until = now + self._block
            bucket.failures.clear()
            return int(self._block.total_seconds())
        return None

    def reset(self, key: str) -> None:
        """Clear an address after it authenticates successfully."""
        self._buckets.pop(key, None)

    def _prune(self, bucket: _Bucket, now: datetime) -> None:
        """Drop failures that fell outside the sliding window."""
        cutoff = now - self._window
        while bucket.failures and bucket.failures[0] < cutoff:
            bucket.failures.popleft()


@lru_cache
def get_login_limiter() -> LoginRateLimiter:
    """The process-wide sign-in limiter, built from settings."""
    settings = get_settings()
    return LoginRateLimiter(
        max_attempts=settings.LOGIN_MAX_ATTEMPTS,
        window=timedelta(minutes=settings.LOGIN_WINDOW_MINUTES),
        block=timedelta(minutes=settings.LOGIN_BLOCK_MINUTES),
    )


def client_ip(request: Request) -> str:
    """Best-effort client address, honouring a proxy when configured.

    Behind nginx the socket peer is always 127.0.0.1, so the real address is
    the first entry of X-Forwarded-For. That header is only trusted when the
    deployment sits behind a proxy — otherwise a caller could forge it to dodge
    the limit — and falls back to the socket peer.
    """
    settings = get_settings()
    if settings.TRUST_PROXY_HEADERS:
        forwarded = request.headers.get("x-forwarded-for")
        if forwarded:
            first = forwarded.split(",")[0].strip()
            if first:
                return first
    return request.client.host if request.client else "unknown"
