"""Brute-force guard: repeated failures from one address get locked out."""
from __future__ import annotations

from datetime import timedelta

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.rate_limit import LoginRateLimiter, get_login_limiter
from tests.conftest import TEST_PASSWORD, create_student

WRONG = {"iin": "060422501511", "password": "wrong-password"}


async def _fail_login(client: AsyncClient) -> int:
    response = await client.post("/api/v1/auth/login", json=WRONG)
    return response.status_code


async def test_repeated_failures_lock_the_address(
    client: AsyncClient, db: AsyncSession
) -> None:
    # Arrange
    await create_student(db)
    limit = get_login_limiter()._max_attempts

    # Act — the first (limit - 1) wrong tries are plain 401s.
    for _ in range(limit - 1):
        assert await _fail_login(client) == 401
    # The attempt that reaches the threshold trips the lock.
    tripping = await client.post("/api/v1/auth/login", json=WRONG)
    # A further attempt is refused outright, before credentials are even checked.
    locked = await client.post("/api/v1/auth/login", json=WRONG)

    # Assert
    assert tripping.status_code == 429
    assert locked.status_code == 429
    assert locked.json()["error"] == "Слишком много попыток входа. Повторите позже"
    assert int(locked.headers["retry-after"]) > 0


async def test_lock_blocks_even_the_correct_password(
    client: AsyncClient, db: AsyncSession
) -> None:
    # Arrange
    await create_student(db)
    limit = get_login_limiter()._max_attempts

    # Act — exhaust the allowance, then offer the real password.
    for _ in range(limit):
        await _fail_login(client)
    response = await client.post(
        "/api/v1/auth/login",
        json={"iin": "060422501511", "password": TEST_PASSWORD},
    )

    # Assert — the lock is on the address, not the credentials.
    assert response.status_code == 429


async def test_a_successful_login_clears_the_counter(
    client: AsyncClient, db: AsyncSession
) -> None:
    # Arrange
    await create_student(db)
    good = {"iin": "060422501511", "password": TEST_PASSWORD}

    # Act — a few misses, then a success, then more misses.
    for _ in range(get_login_limiter()._max_attempts - 1):
        await _fail_login(client)
    assert (await client.post("/api/v1/auth/login", json=good)).status_code == 200
    # After the reset the next wrong try is an ordinary 401, not a lock.
    after = await client.post("/api/v1/auth/login", json=WRONG)

    # Assert
    assert after.status_code == 401


def test_limiter_unlocks_after_the_block_elapses() -> None:
    # Arrange — a limiter whose window and block are already in the past.
    limiter = LoginRateLimiter(
        max_attempts=2, window=timedelta(seconds=0), block=timedelta(seconds=0)
    )

    # Act
    limiter.record_failure("1.2.3.4")
    limiter.record_failure("1.2.3.4")  # trips the lock

    # Assert — a zero-length block has already lapsed, so the address is free.
    assert limiter.retry_after("1.2.3.4") is None


def test_limiter_isolates_addresses() -> None:
    # Arrange
    limiter = LoginRateLimiter(
        max_attempts=2, window=timedelta(minutes=15), block=timedelta(minutes=15)
    )

    # Act — trip one address only.
    limiter.record_failure("10.0.0.1")
    limiter.record_failure("10.0.0.1")

    # Assert — a different address is unaffected.
    assert limiter.retry_after("10.0.0.1") is not None
    assert limiter.retry_after("10.0.0.2") is None
