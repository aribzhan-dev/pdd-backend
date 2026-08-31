"""FastAPI dependencies: the database session, the caller and role guards."""
from __future__ import annotations

from typing import Annotated

import jwt
from fastapi import Depends, Query
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.db import get_db
from app.core.exceptions import (
    AccessExpiredError,
    AccountInactiveError,
    InvalidCredentialsError,
    PermissionDeniedError,
    SessionSupersededError,
)
from app.core.security import decode_token
from app.enums.language import DEFAULT_LANGUAGE, Language
from app.enums.role import STAFF_ROLES, UserRole
from app.models.user import User
from app.repositories.user import UserRepository

_bearer = HTTPBearer(auto_error=False)

DbSession = Annotated[AsyncSession, Depends(get_db)]


async def get_current_user(
    session: DbSession,
    credentials: Annotated[
        HTTPAuthorizationCredentials | None, Depends(_bearer)
    ] = None,
) -> User:
    """Resolve the bearer token to a live account.

    The token alone is not enough: status and access deadline are re-read from
    the database, so revoking a student's access takes effect at once instead
    of waiting for the token to expire.
    """
    if credentials is None:
        raise InvalidCredentialsError("Требуется авторизация")

    try:
        payload = decode_token(credentials.credentials)
    except jwt.InvalidTokenError as exc:
        raise InvalidCredentialsError("Недействительный токен") from exc

    user = await UserRepository(session).get_by_id(int(payload["sub"]))
    if user is None or not user.is_active:
        raise AccountInactiveError

    # One account, one device: a login elsewhere replaced this session id.
    if user.session_id and payload.get("sid") != user.session_id:
        raise SessionSupersededError

    if user.role is UserRole.STUDENT:
        profile = user.student_profile
        if profile is None:
            raise AccountInactiveError("Профиль студента не найден")
        if profile.is_expired:
            raise AccessExpiredError
        if not profile.can_sign_in:
            raise AccountInactiveError(
                f"Статус аккаунта: {profile.effective_status.label}"
            )
    return user


CurrentUserDep = Annotated[User, Depends(get_current_user)]


async def require_admin(user: CurrentUserDep) -> User:
    """Allow only administrators."""
    if user.role is not UserRole.ADMIN:
        raise PermissionDeniedError("Доступно только администратору")
    return user


async def require_staff(user: CurrentUserDep) -> User:
    """Allow administrators and managers."""
    if user.role not in STAFF_ROLES:
        raise PermissionDeniedError("Доступно только сотрудникам")
    return user


async def require_student(user: CurrentUserDep) -> User:
    """Allow only students — the people who actually take tests."""
    if user.role is not UserRole.STUDENT:
        raise PermissionDeniedError("Доступно только студентам")
    return user


AdminDep = Annotated[User, Depends(require_admin)]
StaffDep = Annotated[User, Depends(require_staff)]
StudentDep = Annotated[User, Depends(require_student)]


def get_language(
    lang: Annotated[Language, Query(description="Content language")] = DEFAULT_LANGUAGE,
) -> Language:
    """Read the requested content language from the query string."""
    return lang


LanguageDep = Annotated[Language, Depends(get_language)]
