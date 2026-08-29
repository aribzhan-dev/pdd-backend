"""Login, token refresh and the current-user payload."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from app.schemas.common import IIN, LabeledValue, ORMModel, Password


class LoginRequest(BaseModel):
    """Credentials. There is no self-registration — accounts are issued."""

    iin: IIN
    password: Password


class TokenPair(BaseModel):
    """Issued on a successful login."""

    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int = Field(description="Access token lifetime in seconds")


class RefreshRequest(BaseModel):
    """Exchange a refresh token for a fresh access token."""

    refresh_token: str


class StudentContext(ORMModel):
    """Study details shown in the header of a student's account."""

    category: LabeledValue
    status: LabeledValue
    access_expires_at: datetime
    days_left: int


class CurrentUser(ORMModel):
    """Who the caller is — the payload behind GET /auth/me."""

    id: int
    iin: str
    name: str
    surname: str
    full_name: str
    phone_number: str | None
    role: LabeledValue
    student: StudentContext | None = None


class LoginResponse(BaseModel):
    """Tokens plus the profile, so the client needs a single round-trip."""

    tokens: TokenPair
    user: CurrentUser


class PasswordChangeRequest(BaseModel):
    """Change one's own password."""

    current_password: Password
    new_password: Password
