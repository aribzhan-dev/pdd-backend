"""Student accounts.

Administrators and managers may create and edit students; only an
administrator may delete one. The permission rules themselves live in the
service, so both layers cannot drift apart.
"""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query, status

from app.api.deps import AdminDep, DbSession, StaffDep
from app.enums.category import CATEGORY_LABELS
from app.enums.student_status import STATUS_LABELS
from app.schemas.common import LabeledValue, Message, Page
from app.schemas.user import (
    CredentialsIssued,
    StudentCreate,
    StudentRead,
    StudentUpdate,
)
from app.services.user import UserService

router = APIRouter(prefix="/students", tags=["students"])


@router.post(
    "", response_model=CredentialsIssued, status_code=status.HTTP_201_CREATED
)
async def create_student(
    payload: StudentCreate, staff: StaffDep, session: DbSession
) -> CredentialsIssued:
    """Issue a student account and return the credentials to hand over.

    The password is echoed back only here — afterwards it is stored hashed.
    """
    return await UserService(session).create_student(staff, payload)


@router.get("", response_model=Page[StudentRead])
async def list_students(
    staff: StaffDep,
    session: DbSession,
    search: Annotated[str | None, Query(max_length=100)] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> Page[StudentRead]:
    """List student accounts, optionally filtered by name, IIN or phone."""
    return await UserService(session).list_students(
        staff, search=search, page=page, limit=limit
    )


@router.get("/options", response_model=dict[str, list[LabeledValue]])
async def read_options(_: StaffDep) -> dict[str, list[LabeledValue]]:
    """Categories and statuses for the student form's dropdowns."""
    return {
        "categories": [
            LabeledValue(value=member.value, label=label)
            for member, label in CATEGORY_LABELS.items()
        ],
        "statuses": [
            LabeledValue(value=member.value, label=label)
            for member, label in STATUS_LABELS.items()
        ],
    }


@router.get("/{student_id}", response_model=StudentRead)
async def read_student(
    student_id: int, staff: StaffDep, session: DbSession
) -> StudentRead:
    """Open one student's record."""
    return await UserService(session).get_student(staff, student_id)


@router.patch("/{student_id}", response_model=StudentRead)
async def update_student(
    student_id: int, payload: StudentUpdate, staff: StaffDep, session: DbSession
) -> StudentRead:
    """Edit a student, including extending the access window."""
    return await UserService(session).update_student(staff, student_id, payload)


@router.delete("/{student_id}", response_model=Message)
async def delete_student(
    student_id: int, admin: AdminDep, session: DbSession
) -> Message:
    """Delete a student. Managers are refused; only an administrator may."""
    await UserService(session).delete_student(admin, student_id)
    return Message(detail="Студент удалён")
