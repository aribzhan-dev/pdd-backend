"""Quiz session and its items.

A session is the unit that survives a page reload: the question set, their
order and every answer given are stored server-side, so reopening the page
restores exactly what the student saw. `QuizItem` holds one question of the
session together with the answer chosen for it, if any.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Integer,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.time import as_utc, utc_now
from app.enums.language import Language
from app.enums.quiz import QuizMode, QuizStatus
from app.models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.question import Question

#: A student may finish as soon as a single question has been answered.
MIN_ANSWERS_TO_FINISH = 1

#: Share of correct answers required to pass.
PASS_RATIO = 0.9


class QuizSession(Base, TimestampMixin):
    """One run through a topic, an exam or the mistake collection."""

    __tablename__ = "quiz_sessions"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=False
    )
    topic_id: Mapped[int | None] = mapped_column(
        ForeignKey("topics.id", ondelete="SET NULL")
    )

    mode: Mapped[QuizMode] = mapped_column(
        Enum(QuizMode, native_enum=False, length=20), nullable=False
    )
    status: Mapped[QuizStatus] = mapped_column(
        Enum(QuizStatus, native_enum=False, length=20),
        default=QuizStatus.IN_PROGRESS,
        nullable=False,
        index=True,
    )
    language: Mapped[Language] = mapped_column(
        Enum(Language, native_enum=False, length=5),
        default=Language.RU,
        nullable=False,
    )

    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    time_seconds: Mapped[int | None] = mapped_column(Integer)
    #: Allotted time for timed modes; None means the run is untimed.
    time_limit_seconds: Mapped[int | None] = mapped_column(Integer)

    items: Mapped[list["QuizItem"]] = relationship(
        back_populates="session",
        cascade="all, delete-orphan",
        order_by="QuizItem.position",
        lazy="selectin",
    )

    @property
    def total_questions(self) -> int:
        """How many questions the session was built with."""
        return len(self.items)

    @property
    def answered_count(self) -> int:
        """How many questions have an answer recorded."""
        return sum(1 for item in self.items if item.answer_id is not None)

    @property
    def correct_count(self) -> int:
        """How many answers were correct."""
        return sum(1 for item in self.items if item.is_correct)

    @property
    def can_finish(self) -> bool:
        """Early finishing is allowed from the first answer on."""
        return self.answered_count >= min(MIN_ANSWERS_TO_FINISH, self.total_questions)

    @property
    def deadline(self) -> datetime | None:
        """When the run must be handed in, for modes that are timed."""
        if self.time_limit_seconds is None:
            return None
        return as_utc(self.started_at) + timedelta(seconds=self.time_limit_seconds)

    @property
    def seconds_left(self) -> int | None:
        """Time remaining, never negative. None when the run is untimed."""
        if self.deadline is None:
            return None
        return max(0, int((self.deadline - utc_now()).total_seconds()))

    @property
    def is_out_of_time(self) -> bool:
        """True once a timed run has run past its deadline."""
        return self.seconds_left == 0 if self.deadline is not None else False

    @property
    def score_percent(self) -> int:
        """Correct answers as a percentage of the whole question set."""
        if not self.total_questions:
            return 0
        return round(self.correct_count / self.total_questions * 100)

    @property
    def is_passed(self) -> bool:
        """Passing is measured against the full set, not only answered ones."""
        if not self.total_questions:
            return False
        return self.correct_count / self.total_questions >= PASS_RATIO


class QuizItem(Base):
    """A question inside a session, plus the answer chosen for it."""

    __tablename__ = "quiz_items"
    __table_args__ = (
        UniqueConstraint("session_id", "position", name="uq_quiz_items_position"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    session_id: Mapped[int] = mapped_column(
        ForeignKey("quiz_sessions.id", ondelete="CASCADE"), index=True, nullable=False
    )
    question_id: Mapped[int] = mapped_column(
        ForeignKey("questions.id", ondelete="CASCADE"), nullable=False
    )
    #: Zero-based slot in the session, fixed when the session is created.
    position: Mapped[int] = mapped_column(Integer, nullable=False)

    answer_id: Mapped[int | None] = mapped_column(
        ForeignKey("answers.id", ondelete="SET NULL")
    )
    is_correct: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    answered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    session: Mapped["QuizSession"] = relationship(back_populates="items")
    question: Mapped["Question"] = relationship(lazy="selectin")

    @property
    def is_answered(self) -> bool:
        """True once the student has picked an option."""
        return self.answer_id is not None
