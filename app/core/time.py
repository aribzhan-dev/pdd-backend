"""UTC helpers.

Timestamps are stored as timezone-aware UTC, but not every backend preserves
the offset on the way back: PostgreSQL does, SQLite does not. Comparing a naive
value read from the database against an aware `now()` raises, so every read of
a stored timestamp goes through `as_utc` first.
"""
from __future__ import annotations

from datetime import UTC, datetime


def utc_now() -> datetime:
    """The current moment, timezone-aware."""
    return datetime.now(UTC)


def as_utc(value: datetime) -> datetime:
    """Return the value as timezone-aware UTC, assuming UTC when naive."""
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
