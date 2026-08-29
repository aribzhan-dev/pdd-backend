"""Sign-in rules: who may log in, and when access lapses."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.enums.category import DrivingCategory
from app.enums.role import UserRole
from app.enums.student_status import StudentStatus
from tests.conftest import TEST_PASSWORD, create_staff, create_student, sign_in


async def test_student_signs_in_and_sees_their_study_context(
    client: AsyncClient, db: AsyncSession
) -> None:
    # Arrange
    await create_student(db, category=DrivingCategory.B_C1, access_days=60)

    # Act
    response = await client.post(
        "/api/v1/auth/login",
        json={"iin": "060422501511", "password": TEST_PASSWORD},
    )

    # Assert
    assert response.status_code == 200, response.text
    user = response.json()["user"]
    assert user["role"] == {"value": "student", "label": "Студент"}
    assert user["student"]["category"] == {"value": "B_C1", "label": "B, C1"}
    assert user["student"]["status"]["label"] == "Активный"
    assert user["student"]["days_left"] >= 59


async def test_wrong_password_is_rejected(
    client: AsyncClient, db: AsyncSession
) -> None:
    # Arrange
    await create_student(db)

    # Act
    response = await client.post(
        "/api/v1/auth/login", json={"iin": "060422501511", "password": "nope123"}
    )

    # Assert
    assert response.status_code == 401
    assert response.json()["error"] == "Неверный ИИН или пароль"


async def test_unknown_iin_gives_the_same_error_as_a_wrong_password(
    client: AsyncClient,
) -> None:
    # Act
    response = await client.post(
        "/api/v1/auth/login", json={"iin": "999999999999", "password": TEST_PASSWORD}
    )

    # Assert — the response must not reveal whether the account exists
    assert response.status_code == 401
    assert response.json()["error"] == "Неверный ИИН или пароль"


async def test_student_cannot_sign_in_after_access_expires(
    client: AsyncClient, db: AsyncSession
) -> None:
    # Arrange
    student = await create_student(db)
    student.student_profile.access_expires_at = datetime.now(UTC) - timedelta(days=1)
    await db.commit()

    # Act
    response = await client.post(
        "/api/v1/auth/login",
        json={"iin": "060422501511", "password": TEST_PASSWORD},
    )

    # Assert
    assert response.status_code == 403
    assert "истёк" in response.json()["error"]


async def test_expired_student_is_kept_in_the_database(db: AsyncSession) -> None:
    # Arrange
    student = await create_student(db)
    profile = student.student_profile

    # Act
    profile.access_expires_at = datetime.now(UTC) - timedelta(days=1)
    await db.commit()

    # Assert — the record survives; only the effective status changes
    assert profile.status is StudentStatus.ACTIVE
    assert profile.effective_status is StudentStatus.EXPIRED
    assert profile.effective_status.label == "Доступ истёк"
    assert profile.days_left == 0


async def test_suspended_student_cannot_sign_in(
    client: AsyncClient, db: AsyncSession
) -> None:
    # Arrange
    await create_student(db, status=StudentStatus.SUSPENDED)

    # Act
    response = await client.post(
        "/api/v1/auth/login",
        json={"iin": "060422501511", "password": TEST_PASSWORD},
    )

    # Assert
    assert response.status_code == 403
    assert "Приостановлен" in response.json()["error"]


async def test_iin_must_be_twelve_digits(client: AsyncClient) -> None:
    # Act
    response = await client.post(
        "/api/v1/auth/login", json={"iin": "12345", "password": TEST_PASSWORD}
    )

    # Assert
    assert response.status_code == 422


async def test_me_returns_the_signed_in_account(
    client: AsyncClient, db: AsyncSession
) -> None:
    # Arrange
    await create_staff(db, "110000000001", UserRole.ADMIN)
    headers = await sign_in(client, "110000000001")

    # Act
    response = await client.get("/api/v1/auth/me", headers=headers)

    # Assert
    assert response.status_code == 200
    assert response.json()["role"]["label"] == "Администратор"


async def test_requests_without_a_token_are_rejected(client: AsyncClient) -> None:
    # Act
    response = await client.get("/api/v1/topics")

    # Assert
    assert response.status_code == 401


async def test_refresh_token_yields_a_working_access_token(
    client: AsyncClient, db: AsyncSession
) -> None:
    # Arrange
    await create_student(db)
    login = await client.post(
        "/api/v1/auth/login",
        json={"iin": "060422501511", "password": TEST_PASSWORD},
    )
    refresh_token = login.json()["tokens"]["refresh_token"]

    # Act
    refreshed = await client.post(
        "/api/v1/auth/refresh", json={"refresh_token": refresh_token}
    )

    # Assert
    assert refreshed.status_code == 200
    access = refreshed.json()["access_token"]
    me = await client.get(
        "/api/v1/auth/me", headers={"Authorization": f"Bearer {access}"}
    )
    assert me.status_code == 200


async def test_access_token_is_not_accepted_as_a_refresh_token(
    client: AsyncClient, db: AsyncSession
) -> None:
    # Arrange
    await create_student(db)
    login = await client.post(
        "/api/v1/auth/login",
        json={"iin": "060422501511", "password": TEST_PASSWORD},
    )

    # Act
    response = await client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": login.json()["tokens"]["access_token"]},
    )

    # Assert
    assert response.status_code == 401
