"""Account management: admins handle managers, staff handle students.

The permission rules live here, in one place:
  * only an admin may touch manager accounts;
  * admins and managers may create and edit students;
  * only an admin may delete a student — a manager never can.
"""
from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import (
    DuplicateIINError,
    NotFoundError,
    PermissionDeniedError,
)
from app.core.security import hash_password
from app.core.time import as_utc, utc_now
from app.enums.role import STAFF_ROLES, UserRole
from app.enums.student_status import StudentStatus
from app.models.student_profile import StudentProfile
from app.models.user import User
from app.repositories.user import UserRepository
from app.schemas.common import Page
from app.schemas.user import (
    CredentialsIssued,
    ManagerCreate,
    ManagerUpdate,
    StudentCreate,
    StudentRead,
    StudentUpdate,
    UserBrief,
)
from app.services.labels import to_labeled


class UserService:
    """Create, list, edit and (for admins) delete accounts."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.users = UserRepository(session)

    # --- Managers (admin only) ---------------------------------------------

    async def create_manager(self, actor: User, data: ManagerCreate) -> UserBrief:
        """Admin issues a manager account."""
        _require_admin(actor, "Управлять менеджерами может только администратор")
        await self._assert_iin_free(data.iin)

        manager = User(
            iin=data.iin,
            password_hash=hash_password(data.password),
            name=data.name,
            surname=data.surname,
            phone_number=data.phone_number,
            role=UserRole.MANAGER,
            created_by_id=actor.id,
        )
        self.users.add(manager)
        await self.session.commit()
        await self.session.refresh(manager)
        return _to_brief(manager)

    async def list_managers(
        self, actor: User, *, search: str | None, page: int, limit: int
    ) -> Page[UserBrief]:
        """Admin lists manager accounts."""
        _require_admin(actor, "Просматривать менеджеров может только администратор")
        rows, total = await self.users.list_by_role(
            UserRole.MANAGER, search=search, page=page, limit=limit
        )
        return Page(
            items=[_to_brief(row) for row in rows],
            total=total,
            page=page,
            limit=limit,
        )

    async def update_manager(
        self, actor: User, manager_id: int, data: ManagerUpdate
    ) -> UserBrief:
        """Admin edits a manager account."""
        _require_admin(actor, "Управлять менеджерами может только администратор")
        manager = await self._get_by_role(manager_id, UserRole.MANAGER)

        if data.name is not None:
            manager.name = data.name
        if data.surname is not None:
            manager.surname = data.surname
        if data.phone_number is not None:
            manager.phone_number = data.phone_number
        if data.password is not None:
            manager.password_hash = hash_password(data.password)
        if data.is_active is not None:
            manager.is_active = data.is_active

        await self.session.commit()
        await self.session.refresh(manager)
        return _to_brief(manager)

    async def delete_manager(self, actor: User, manager_id: int) -> None:
        """Admin removes a manager account."""
        _require_admin(actor, "Удалять менеджеров может только администратор")
        manager = await self._get_by_role(manager_id, UserRole.MANAGER)
        await self.users.delete(manager)
        await self.session.commit()

    # --- Students (admin and manager) --------------------------------------

    async def create_student(
        self, actor: User, data: StudentCreate
    ) -> CredentialsIssued:
        """Issue a student account and return the credentials to hand over.

        The plain password is echoed back exactly once, here, because staff
        need to pass it to the student; it is never readable again.
        """
        _require_staff(actor)
        await self._assert_iin_free(data.iin)

        now = utc_now()
        expires_at = data.access_expires_at or now + timedelta(
            days=data.access_days or 0
        )

        student = User(
            iin=data.iin,
            password_hash=hash_password(data.password),
            name=data.name,
            surname=data.surname,
            phone_number=data.phone_number,
            role=UserRole.STUDENT,
            created_by_id=actor.id,
        )
        self.users.add(student)
        await self.session.flush()

        self.users.add_profile(
            StudentProfile(
                user_id=student.id,
                category=data.category,
                status=StudentStatus.ACTIVE,
                access_starts_at=now,
                access_expires_at=expires_at,
                note=data.note,
            )
        )
        await self.session.commit()

        return CredentialsIssued(
            iin=student.iin,
            password=data.password,
            full_name=student.full_name,
        )

    async def list_students(
        self, actor: User, *, search: str | None, page: int, limit: int
    ) -> Page[StudentRead]:
        """Staff lists student accounts."""
        _require_staff(actor)
        rows, total = await self.users.list_by_role(
            UserRole.STUDENT, search=search, page=page, limit=limit
        )
        return Page(
            items=[_to_student(row) for row in rows],
            total=total,
            page=page,
            limit=limit,
        )

    async def get_student(self, actor: User, student_id: int) -> StudentRead:
        """Staff opens one student's record."""
        _require_staff(actor)
        return _to_student(await self._get_by_role(student_id, UserRole.STUDENT))

    async def update_student(
        self, actor: User, student_id: int, data: StudentUpdate
    ) -> StudentRead:
        """Staff edits a student, including extending their access window."""
        _require_staff(actor)
        student = await self._get_by_role(student_id, UserRole.STUDENT)
        profile = student.student_profile
        if profile is None:
            raise NotFoundError("Профиль студента не найден")

        if data.name is not None:
            student.name = data.name
        if data.surname is not None:
            student.surname = data.surname
        if data.phone_number is not None:
            student.phone_number = data.phone_number
        if data.password is not None:
            student.password_hash = hash_password(data.password)

        if data.category is not None:
            profile.category = data.category
        if data.status is not None:
            profile.status = data.status
        if data.note is not None:
            profile.note = data.note
        if data.access_expires_at is not None:
            profile.access_expires_at = data.access_expires_at
        if data.extend_days is not None:
            profile.access_expires_at = _extend(
                profile.access_expires_at, data.extend_days
            )
            if profile.status is StudentStatus.EXPIRED:
                profile.status = StudentStatus.ACTIVE

        await self.session.commit()
        await self.session.refresh(student)
        return _to_student(student)

    async def delete_student(self, actor: User, student_id: int) -> None:
        """Only an admin may delete a student; managers are refused."""
        _require_admin(actor, "Удалять студентов может только администратор")
        student = await self._get_by_role(student_id, UserRole.STUDENT)
        await self.users.delete(student)
        await self.session.commit()

    # --- Internals ---------------------------------------------------------

    async def _assert_iin_free(self, iin: str) -> None:
        """Fail early when the IIN is already registered."""
        if await self.users.iin_exists(iin):
            raise DuplicateIINError

    async def _get_by_role(self, user_id: int, role: UserRole) -> User:
        """Load an account and confirm it really has the expected role."""
        user = await self.users.get_by_id(user_id)
        if user is None or user.role is not role:
            raise NotFoundError
        return user


def _require_admin(actor: User, message: str) -> None:
    """Guard for admin-only operations."""
    if actor.role is not UserRole.ADMIN:
        raise PermissionDeniedError(message)


def _require_staff(actor: User) -> None:
    """Guard for operations open to admins and managers."""
    if actor.role not in STAFF_ROLES:
        raise PermissionDeniedError


def _extend(current_expiry: datetime, days: int) -> datetime:
    """Extend an access window, starting from now if it already lapsed."""
    base = max(as_utc(current_expiry), utc_now())
    return base + timedelta(days=days)


def _to_brief(user: User) -> UserBrief:
    """Compact row for staff listings."""
    return UserBrief(
        id=user.id,
        iin=user.iin,
        full_name=user.full_name,
        phone_number=user.phone_number,
        role=to_labeled(user.role),
        is_active=user.is_active,
        created_at=user.created_at,
    )


def _to_student(user: User) -> StudentRead:
    """Full student record for the staff area."""
    profile = user.student_profile
    if profile is None:
        raise NotFoundError("Профиль студента не найден")
    return StudentRead(
        id=user.id,
        iin=user.iin,
        name=user.name,
        surname=user.surname,
        full_name=user.full_name,
        phone_number=user.phone_number,
        is_active=user.is_active,
        category=to_labeled(profile.category),
        status=to_labeled(profile.effective_status),
        access_starts_at=profile.access_starts_at,
        access_expires_at=profile.access_expires_at,
        days_left=profile.days_left,
        note=profile.note,
        last_login_at=user.last_login_at,
        created_at=user.created_at,
    )
