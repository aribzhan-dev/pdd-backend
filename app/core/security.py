"""Password hashing and JWT issuing/verification.

Hashing is bcrypt with a SHA-256 pre-hash (the "bcrypt_sha256" scheme). bcrypt
silently ignores everything past 72 bytes, so the password is digested first;
the digest is base64-encoded to 44 bytes, which fits comfortably and keeps the
full entropy of long passwords.

Access tokens carry the role so routing decisions need no extra query, but
anything that can change mid-session — account status, access deadline — is
re-read from the database on every request.
"""
from __future__ import annotations

import base64
import hashlib
from datetime import UTC, datetime, timedelta
from typing import Any, Literal

import bcrypt
import jwt

from app.core.config import get_settings

settings = get_settings()

TokenType = Literal["access", "refresh"]

#: Marks hashes produced by this module, so a future scheme change is detectable.
_SCHEME_PREFIX = "bcrypt_sha256$"


def _prepare(plain_password: str) -> bytes:
    """Reduce a password of any length to a fixed 44-byte bcrypt input."""
    digest = hashlib.sha256(plain_password.encode("utf-8")).digest()
    return base64.b64encode(digest)


def hash_password(plain_password: str) -> str:
    """Return a storable hash. Plain passwords are never persisted."""
    hashed = bcrypt.hashpw(_prepare(plain_password), bcrypt.gensalt())
    return _SCHEME_PREFIX + hashed.decode("ascii")


def verify_password(plain_password: str, password_hash: str) -> bool:
    """Check a candidate password against a stored hash.

    Returns False rather than raising on a malformed hash, so a corrupted row
    fails the login instead of the whole request.
    """
    if not password_hash.startswith(_SCHEME_PREFIX):
        return False
    stored = password_hash[len(_SCHEME_PREFIX) :].encode("ascii")
    try:
        return bcrypt.checkpw(_prepare(plain_password), stored)
    except ValueError:
        return False


def _create_token(
    subject: str, role: str, token_type: TokenType, expires_delta: timedelta
) -> str:
    """Sign a JWT for the given subject with an explicit expiry."""
    now = datetime.now(UTC)
    payload: dict[str, Any] = {
        "sub": subject,
        "role": role,
        "type": token_type,
        "iat": now,
        "exp": now + expires_delta,
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def create_access_token(user_id: int, role: str) -> str:
    """Short-lived token sent with every API call."""
    return _create_token(
        str(user_id),
        role,
        "access",
        timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
    )


def create_refresh_token(user_id: int, role: str) -> str:
    """Long-lived token used only to mint new access tokens."""
    return _create_token(
        str(user_id),
        role,
        "refresh",
        timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
    )


def decode_token(token: str, expected_type: TokenType = "access") -> dict[str, Any]:
    """Decode and validate a JWT.

    Raises jwt.InvalidTokenError when the signature, expiry or token type is
    wrong, so callers can treat every failure identically.
    """
    payload: dict[str, Any] = jwt.decode(
        token, settings.SECRET_KEY, algorithms=[settings.JWT_ALGORITHM]
    )
    if payload.get("type") != expected_type:
        raise jwt.InvalidTokenError(
            f"Expected a {expected_type} token, got {payload.get('type')!r}"
        )
    return payload
