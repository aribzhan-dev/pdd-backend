"""Database access for accounts and student profiles."""
from __future__ import annotations

from sqlalchemy import Select, func, or_, select
from sqlalchemy.orm import selectinload

from app.enums.role import UserRole
from app.models.student_profile import StudentProfile
from app.models.user import User
from app.repositories.base import BaseRepository


class UserRepository(BaseRepository):
    """Queries over `users` and the student profile attached to them."""

    async def get_by_id(self, user_id: int) -> User | None:
        """Load one account with its student profile, if any."""
        stmt = (
            select(User)
            .where(User.id == user_id)
            .options(selectinload(User.student_profile))
        )
        return await self.session.scalar(stmt)

    async def get_by_iin(self, iin: str) -> User | None:
        """Load the account used for signing in."""
        stmt = (
            select(User)
            .where(User.iin == iin)
            .options(selectinload(User.student_profile))
        )
        return await self.session.scalar(stmt)

    async def iin_exists(self, iin: str) -> bool:
        """True when the IIN is already taken."""
        return await self.session.scalar(
            select(func.count()).select_from(User).where(User.iin == iin)
        ) > 0

    def _search_stmt(self, role: UserRole, search: str | None) -> Select:
        """Build the filtered listing query for one role."""
        stmt = select(User).where(User.role == role)
        if search:
            pattern = f"%{search.strip()}%"
            stmt = stmt.where(
                or_(
                    User.iin.ilike(pattern),
                    User.name.ilike(pattern),
                    User.surname.ilike(pattern),
                    User.phone_number.ilike(pattern),
                )
            )
        return stmt

    async def list_by_role(
        self,
        role: UserRole,
        *,
        search: str | None = None,
        page: int = 1,
        limit: int = 20,
    ) -> tuple[list[User], int]:
        """Return one page of accounts for a role, plus the total count."""
        stmt = self._search_stmt(role, search)
        total = await self.session.scalar(
            select(func.count()).select_from(stmt.subquery())
        )
        rows = await self.session.scalars(
            stmt.options(selectinload(User.student_profile))
            .order_by(User.created_at.desc())
            .offset((page - 1) * limit)
            .limit(limit)
        )
        return list(rows), int(total or 0)

    def add(self, user: User) -> User:
        """Stage a new account; the caller commits."""
        self.session.add(user)
        return user

    def add_profile(self, profile: StudentProfile) -> StudentProfile:
        """Stage a new student profile; the caller commits."""
        self.session.add(profile)
        return profile

    async def delete(self, user: User) -> None:
        """Remove an account. Only an admin ever reaches this."""
        await self.session.delete(user)
