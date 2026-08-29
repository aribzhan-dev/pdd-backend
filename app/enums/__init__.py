"""Shared enumerations used across models, schemas and services."""
from app.enums.category import CATEGORY_LABELS, DrivingCategory
from app.enums.language import DEFAULT_LANGUAGE, Language
from app.enums.quiz import (
    QUIZ_MODE_LABELS,
    QUIZ_STATUS_LABELS,
    QuizMode,
    QuizStatus,
)
from app.enums.role import ROLE_LABELS, STAFF_ROLES, UserRole
from app.enums.student_status import (
    LOGIN_ALLOWED_STATUSES,
    STATUS_LABELS,
    StudentStatus,
)

__all__ = [
    "CATEGORY_LABELS",
    "DEFAULT_LANGUAGE",
    "DrivingCategory",
    "LOGIN_ALLOWED_STATUSES",
    "Language",
    "QUIZ_MODE_LABELS",
    "QUIZ_STATUS_LABELS",
    "QuizMode",
    "QuizStatus",
    "ROLE_LABELS",
    "STAFF_ROLES",
    "STATUS_LABELS",
    "StudentStatus",
    "UserRole",
]
