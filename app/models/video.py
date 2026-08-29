"""Standalone teaching videos (YouTube lessons), independent of questions."""
from __future__ import annotations

from sqlalchemy import Boolean, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin


class Video(Base, TimestampMixin):
    """A lesson video shown in the learning section."""

    __tablename__ = "videos"

    id: Mapped[int] = mapped_column(primary_key=True)
    title_ru: Mapped[str] = mapped_column(String(300), nullable=False)
    title_kz: Mapped[str | None] = mapped_column(String(300))
    youtube_url: Mapped[str] = mapped_column(String(500), nullable=False)
    order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
