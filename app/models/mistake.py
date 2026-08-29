"""Per-student mistake collection.

A question enters the collection when answered wrongly and leaves it once
answered correctly, so "work on mistakes" always reflects current weak spots.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Mistake(Base):
    """One question a given student is currently getting wrong."""

    __tablename__ = "mistakes"
    __table_args__ = (
        UniqueConstraint("user_id", "question_id", name="uq_mistakes_user_question"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    question_id: Mapped[int] = mapped_column(
        ForeignKey("questions.id", ondelete="CASCADE"), nullable=False
    )
    wrong_count: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    last_wrong_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
