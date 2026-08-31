"""Authentication: signing in, refreshing tokens and reading one's profile.

There is no self-registration — every account is issued by staff. A student's
right to sign in is re-checked here on every login and on every token refresh,
so revoking access takes effect immediately rather than at token expiry.
"""
from __future__ import annotations

import jwt
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.time import utc_now
from app.core.exceptions import (
    AccessExpiredError,
    AccountInactiveError,
    InvalidCredentialsError,
    SessionSupersededError,
)
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    new_session_id,
    verify_password,
)
from app.enums.role import UserRole
from app.models.user import User
from app.repositories.user import UserRepository
from app.schemas.auth import (
    CurrentUser,
    LoginResponse,
    StudentContext,
    TokenPair,
)
from app.services.labels import to_labeled

settings = get_settings()


class AuthService:
    """Everything behind the /auth endpoints."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.users = UserRepository(session)

    async def login(self, iin: str, password: str) -> LoginResponse:
        """Verify credentials and issue a token pair.

        A wrong IIN and a wrong password produce the same error, so the
        response does not reveal which accounts exist.
        """
        user = await self.users.get_by_iin(iin)
        if user is None or not verify_password(password, user.password_hash):
            raise InvalidCredentialsError
        self._assert_may_sign_in(user)

        # A fresh session id invalidates whatever was issued to another
        # device: one account signs in on one device at a time.
        user.session_id = new_session_id()
        user.last_login_at = utc_now()
        await self.session.commit()
        return LoginResponse(tokens=self._issue_tokens(user), user=build_profile(user))

    async def refresh(self, refresh_token: str) -> TokenPair:
        """Exchange a refresh token for a new pair, re-checking access."""
        try:
            payload = decode_token(refresh_token, expected_type="refresh")
        except jwt.InvalidTokenError as exc:
            raise InvalidCredentialsError("Недействительный токен") from exc

        user = await self.users.get_by_id(int(payload["sub"]))
        if user is None:
            raise InvalidCredentialsError
        # Refreshing must not resurrect a device that a newer login replaced.
        if payload.get("sid") != user.session_id:
            raise SessionSupersededError
        self._assert_may_sign_in(user)
        return self._issue_tokens(user)

    async def change_password(
        self, user: User, current_password: str, new_password: str
    ) -> None:
        """Let a signed-in user replace their own password."""
        if not verify_password(current_password, user.password_hash):
            raise InvalidCredentialsError("Текущий пароль указан неверно")
        user.password_hash = hash_password(new_password)
        await self.session.commit()

    @staticmethod
    def _assert_may_sign_in(user: User) -> None:
        """Reject deactivated accounts and students past their deadline."""
        if not user.is_active:
            raise AccountInactiveError
        if user.role is not UserRole.STUDENT:
            return

        profile = user.student_profile
        if profile is None:
            raise AccountInactiveError("Профиль студента не найден")
        if profile.is_expired:
            raise AccessExpiredError
        if not profile.can_sign_in:
            raise AccountInactiveError(
                f"Статус аккаунта: {profile.effective_status.label}"
            )

    @staticmethod
    def _issue_tokens(user: User) -> TokenPair:
        """Mint an access/refresh pair for an already-authorised user."""
        session_id = user.session_id or ""
        return TokenPair(
            access_token=create_access_token(user.id, user.role.value, session_id),
            refresh_token=create_refresh_token(user.id, user.role.value, session_id),
            expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        )


def build_profile(user: User) -> CurrentUser:
    """Shape an account for the client, including a student's study context.

    The student block is what the header shows: name, category and how much
    access is left.
    """
    student: StudentContext | None = None
    profile = user.student_profile
    if user.role is UserRole.STUDENT and profile is not None:
        student = StudentContext(
            category=to_labeled(profile.category),
            status=to_labeled(profile.effective_status),
            access_expires_at=profile.access_expires_at,
            days_left=profile.days_left,
        )

    return CurrentUser(
        id=user.id,
        iin=user.iin,
        name=user.name,
        surname=user.surname,
        full_name=user.full_name,
        phone_number=user.phone_number,
        role=to_labeled(user.role),
        student=student,
    )
