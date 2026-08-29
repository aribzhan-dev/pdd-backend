"""User roles. Role identifiers are English; display labels are Russian."""
from __future__ import annotations

import enum


class UserRole(str, enum.Enum):
    """Who a user is and, implicitly, what they may do.

    ADMIN   — full control: manages managers and students.
    MANAGER — may create and edit students, but never delete them.
    STUDENT — may only take tests and read their own history.
    """

    ADMIN = "admin"
    MANAGER = "manager"
    STUDENT = "student"

    @property
    def label(self) -> str:
        """Human-readable name shown in the UI (Russian)."""
        return ROLE_LABELS[self]


ROLE_LABELS: dict[UserRole, str] = {
    UserRole.ADMIN: "Администратор",
    UserRole.MANAGER: "Менеджер",
    UserRole.STUDENT: "Студент",
}

#: Roles allowed to manage students (create / edit).
STAFF_ROLES: frozenset[UserRole] = frozenset({UserRole.ADMIN, UserRole.MANAGER})
