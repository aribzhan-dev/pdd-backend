"""Shared repository plumbing."""
from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession


class BaseRepository:
    """Holds the session every repository works through."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
