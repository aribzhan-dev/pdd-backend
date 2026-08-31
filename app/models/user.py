"""Account model — one row per person who can sign in.

Identity is the IIN (Kazakhstan individual identification number): it is the
login for every role. Role-specific data lives in a separate profile table so
this model stays about authentication only.
"""
from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, Enum, Index, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.enums.role import UserRole
from app.models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.student_profile import StudentProfile

#: Length of a Kazakhstan IIN — exactly 12 digits.
IIN_LENGTH = 12


class User(Base, TimestampMixin):
    """A person who can sign in. There is no self-registration by design."""

    __tablename__ = "users"
    __table_args__ = (Index("ix_users_role_active", "role", "is_active"),)

    id: Mapped[int] = mapped_column(primary_key=True)

    # --- Credentials ---
    iin: Mapped[str] = mapped_column(
        String(IIN_LENGTH), unique=True, index=True, nullable=False
    )
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)

    # --- Identity ---
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    surname: Mapped[str] = mapped_column(String(100), nullable=False)
    phone_number: Mapped[str | None] = mapped_column(String(20))

    # --- Authorisation ---
    role: Mapped[UserRole] = mapped_column(
        Enum(UserRole, native_enum=False, length=20), nullable=False
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    #: Identifies the one sign-in that is currently valid. Every login mints a
    #: new value and stamps it into the token, so tokens issued to any earlier
    #: device stop matching and are refused — one account, one device.
    session_id: Mapped[str | None] = mapped_column(String(36))

    # --- Audit: which staff member created this account ---
    created_by_id: Mapped[int | None] = mapped_column(index=True)

    student_profile: Mapped["StudentProfile | None"] = relationship(
        back_populates="user", cascade="all, delete-orphan", uselist=False
    )

    @property
    def full_name(self) -> str:
        """Surname first, matching how names are shown in the UI."""
        return f"{self.surname} {self.name}".strip()
