"""Lifecycle status of a student account."""
from __future__ import annotations

import enum


class StudentStatus(str, enum.Enum):
    """A student is never deleted — the status records where they stand.

    ACTIVE    — access is open and not expired.
    SUSPENDED — access paused manually by staff.
    EXPIRED   — the access window ran out; the record is kept for history.
    GRADUATED — finished the programme.
    """

    ACTIVE = "active"
    SUSPENDED = "suspended"
    EXPIRED = "expired"
    GRADUATED = "graduated"

    @property
    def label(self) -> str:
        """Human-readable name shown in the UI (Russian)."""
        return STATUS_LABELS[self]


STATUS_LABELS: dict[StudentStatus, str] = {
    StudentStatus.ACTIVE: "Активный",
    StudentStatus.SUSPENDED: "Приостановлен",
    StudentStatus.EXPIRED: "Доступ истёк",
    StudentStatus.GRADUATED: "Обучение завершено",
}

#: Statuses that still permit signing in (subject to the access deadline).
LOGIN_ALLOWED_STATUSES: frozenset[StudentStatus] = frozenset({StudentStatus.ACTIVE})
