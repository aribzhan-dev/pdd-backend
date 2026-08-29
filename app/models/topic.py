"""Topic — a numbered chapter of the traffic-rules curriculum."""
from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import Boolean, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.question import Question


class Topic(Base, TimestampMixin):
    """A group of questions, shown on the catalogue screen."""

    __tablename__ = "topics"

    id: Mapped[int] = mapped_column(primary_key=True)
    number: Mapped[int] = mapped_column(Integer, nullable=False, index=True)

    title_ru: Mapped[str] = mapped_column(String(300), nullable=False)
    title_kz: Mapped[str | None] = mapped_column(String(300))
    description_ru: Mapped[str | None] = mapped_column(Text)
    description_kz: Mapped[str | None] = mapped_column(Text)

    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    questions: Mapped[list["Question"]] = relationship(
        back_populates="topic",
        cascade="all, delete-orphan",
        order_by="Question.order",
    )
