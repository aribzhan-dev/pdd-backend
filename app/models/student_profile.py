"""Student-specific data: study programme, status and the access window.

Access is a deadline, not a deletion: once `access_expires_at` passes the
student can no longer sign in, but the record — and their whole test history —
stays in the database.
"""
from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Enum, ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.time import as_utc, utc_now
from app.enums.category import DrivingCategory
from app.enums.student_status import LOGIN_ALLOWED_STATUSES, StudentStatus
from app.models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.user import User


class StudentProfile(Base, TimestampMixin):
    """The study record attached to a student account."""

    __tablename__ = "student_profiles"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        unique=True,
        index=True,
        nullable=False,
    )

    category: Mapped[DrivingCategory] = mapped_column(
        Enum(DrivingCategory, native_enum=False, length=20), nullable=False
    )
    status: Mapped[StudentStatus] = mapped_column(
        Enum(StudentStatus, native_enum=False, length=20),
        default=StudentStatus.ACTIVE,
        nullable=False,
        index=True,
    )

    # --- Access window ---
    access_starts_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    access_expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )

    note: Mapped[str | None] = mapped_column(Text)

    user: Mapped["User"] = relationship(back_populates="student_profile")

    @property
    def is_expired(self) -> bool:
        """True once the access deadline has passed."""
        return utc_now() >= as_utc(self.access_expires_at)

    @property
    def days_left(self) -> int:
        """Whole days of access remaining, never negative."""
        remaining = as_utc(self.access_expires_at) - utc_now()
        return max(0, remaining.days)

    @property
    def can_sign_in(self) -> bool:
        """A student may sign in only while active and inside the window."""
        return self.status in LOGIN_ALLOWED_STATUSES and not self.is_expired

    @property
    def effective_status(self) -> StudentStatus:
        """Status as it should be shown: an active-but-lapsed student is EXPIRED."""
        if self.status is StudentStatus.ACTIVE and self.is_expired:
            return StudentStatus.EXPIRED
        return self.status
