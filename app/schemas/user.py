"""Schemas for managing staff and student accounts."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field, model_validator

from app.enums.category import DrivingCategory
from app.enums.student_status import StudentStatus
from app.schemas.common import (
    IIN,
    LabeledValue,
    ORMModel,
    Password,
    PersonName,
    PhoneNumber,
)

#: Bounds on the access window staff may grant, in days.
MIN_ACCESS_DAYS = 1
MAX_ACCESS_DAYS = 730


class ManagerCreate(BaseModel):
    """Admin creates a manager account."""

    iin: IIN
    password: Password
    name: PersonName
    surname: PersonName
    phone_number: PhoneNumber | None = None


class ManagerUpdate(BaseModel):
    """Admin edits a manager. Omitted fields are left untouched."""

    name: PersonName | None = None
    surname: PersonName | None = None
    phone_number: PhoneNumber | None = None
    password: Password | None = None
    is_active: bool | None = None


class StudentCreate(BaseModel):
    """Staff issues a student account, including its credentials.

    The access window may be given either as a duration in days or as an
    explicit expiry date; exactly one of the two is required.
    """

    iin: IIN
    password: Password
    name: PersonName
    surname: PersonName
    phone_number: PhoneNumber | None = None
    category: DrivingCategory
    access_days: int | None = Field(
        default=None, ge=MIN_ACCESS_DAYS, le=MAX_ACCESS_DAYS
    )
    access_expires_at: datetime | None = None
    note: str | None = None

    @model_validator(mode="after")
    def check_access_window(self) -> "StudentCreate":
        """Require exactly one way of expressing the access window."""
        given = [self.access_days is not None, self.access_expires_at is not None]
        if sum(given) != 1:
            raise ValueError(
                "Provide exactly one of access_days or access_expires_at"
            )
        return self


class StudentUpdate(BaseModel):
    """Staff edits a student. Omitted fields are left untouched."""

    name: PersonName | None = None
    surname: PersonName | None = None
    phone_number: PhoneNumber | None = None
    password: Password | None = None
    category: DrivingCategory | None = None
    status: StudentStatus | None = None
    access_expires_at: datetime | None = None
    extend_days: int | None = Field(default=None, ge=1, le=MAX_ACCESS_DAYS)
    note: str | None = None


class UserBrief(ORMModel):
    """Compact account row for list screens."""

    id: int
    iin: str
    full_name: str
    phone_number: str | None
    role: LabeledValue
    is_active: bool
    created_at: datetime


class StudentRead(ORMModel):
    """Full student record for the staff area."""

    id: int
    iin: str
    name: str
    surname: str
    full_name: str
    phone_number: str | None
    is_active: bool
    category: LabeledValue
    status: LabeledValue
    access_starts_at: datetime
    access_expires_at: datetime
    days_left: int
    note: str | None
    last_login_at: datetime | None
    created_at: datetime


class CredentialsIssued(BaseModel):
    """Returned once at creation so staff can hand the login over."""

    iin: str
    password: str
    full_name: str
