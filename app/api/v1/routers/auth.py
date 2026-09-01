"""Sign-in endpoints. There is no registration route by design."""
from __future__ import annotations

from fastapi import APIRouter, Request, status

from app.api.deps import CurrentUserDep, DbSession
from app.core.exceptions import InvalidCredentialsError, TooManyAttemptsError
from app.core.rate_limit import client_ip, get_login_limiter
from app.schemas.auth import (
    CurrentUser,
    LoginRequest,
    LoginResponse,
    PasswordChangeRequest,
    RefreshRequest,
    TokenPair,
)
from app.schemas.common import Message
from app.services.auth import AuthService, build_profile

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=LoginResponse)
async def login(
    payload: LoginRequest, request: Request, session: DbSession
) -> LoginResponse:
    """Sign in with an IIN and password issued by staff.

    Repeated failures from one address are throttled: after a handful of wrong
    tries the address is locked out for a cool-off period, so the credentials
    cannot be guessed by brute force.
    """
    limiter = get_login_limiter()
    ip = client_ip(request)

    locked_for = limiter.retry_after(ip)
    if locked_for is not None:
        raise TooManyAttemptsError(retry_after=locked_for)

    try:
        result = await AuthService(session).login(payload.iin, payload.password)
    except InvalidCredentialsError:
        # A failed try counts; crossing the threshold locks the address.
        blocked_for = limiter.record_failure(ip)
        if blocked_for is not None:
            raise TooManyAttemptsError(retry_after=blocked_for) from None
        raise

    limiter.reset(ip)
    return result


@router.post("/refresh", response_model=TokenPair)
async def refresh(payload: RefreshRequest, session: DbSession) -> TokenPair:
    """Exchange a refresh token for a new token pair."""
    return await AuthService(session).refresh(payload.refresh_token)


@router.get("/me", response_model=CurrentUser)
async def read_me(user: CurrentUserDep) -> CurrentUser:
    """The signed-in account, including a student's category and access."""
    return build_profile(user)


@router.post(
    "/password", response_model=Message, status_code=status.HTTP_200_OK
)
async def change_password(
    payload: PasswordChangeRequest, user: CurrentUserDep, session: DbSession
) -> Message:
    """Replace one's own password."""
    await AuthService(session).change_password(
        user, payload.current_password, payload.new_password
    )
    return Message(detail="Пароль обновлён")
