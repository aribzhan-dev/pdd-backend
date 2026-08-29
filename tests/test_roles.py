"""Role boundaries: who may create, edit and delete whom."""
from __future__ import annotations

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.enums.role import UserRole
from tests.conftest import create_staff, create_student, sign_in

ADMIN_IIN = "110000000001"
MANAGER_IIN = "220000000002"
STUDENT_IIN = "060422501511"

NEW_STUDENT = {
    "iin": "330000000003",
    "password": "student-pass-1",
    "name": "Айдос",
    "surname": "Серикулы",
    "phone_number": "+77011234567",
    "category": "B_C1",
    "access_days": 60,
}


async def test_admin_creates_a_manager(client: AsyncClient, db: AsyncSession) -> None:
    # Arrange
    await create_staff(db, ADMIN_IIN, UserRole.ADMIN)
    headers = await sign_in(client, ADMIN_IIN)

    # Act
    response = await client.post(
        "/api/v1/managers",
        headers=headers,
        json={
            "iin": MANAGER_IIN,
            "password": "manager-pass-1",
            "name": "Дана",
            "surname": "Абаева",
        },
    )

    # Assert
    assert response.status_code == 201, response.text
    assert response.json()["role"] == {"value": "manager", "label": "Менеджер"}


async def test_manager_cannot_manage_other_managers(
    client: AsyncClient, db: AsyncSession
) -> None:
    # Arrange
    await create_staff(db, MANAGER_IIN, UserRole.MANAGER)
    headers = await sign_in(client, MANAGER_IIN)

    # Act
    listed = await client.get("/api/v1/managers", headers=headers)
    created = await client.post(
        "/api/v1/managers",
        headers=headers,
        json={"iin": "440000000004", "password": "x-pass-1", "name": "A", "surname": "B"},
    )

    # Assert
    assert listed.status_code == 403
    assert created.status_code == 403


async def test_staff_create_a_student_and_receive_the_credentials(
    client: AsyncClient, db: AsyncSession
) -> None:
    # Arrange
    await create_staff(db, MANAGER_IIN, UserRole.MANAGER)
    headers = await sign_in(client, MANAGER_IIN)

    # Act
    response = await client.post(
        "/api/v1/students", headers=headers, json=NEW_STUDENT
    )

    # Assert — the plain password comes back exactly once, to hand over
    assert response.status_code == 201, response.text
    issued = response.json()
    assert issued["iin"] == NEW_STUDENT["iin"]
    assert issued["password"] == NEW_STUDENT["password"]
    assert issued["full_name"] == "Серикулы Айдос"


async def test_the_issued_student_can_sign_in(
    client: AsyncClient, db: AsyncSession
) -> None:
    # Arrange
    await create_staff(db, ADMIN_IIN, UserRole.ADMIN)
    staff_headers = await sign_in(client, ADMIN_IIN)
    await client.post("/api/v1/students", headers=staff_headers, json=NEW_STUDENT)

    # Act
    response = await client.post(
        "/api/v1/auth/login",
        json={"iin": NEW_STUDENT["iin"], "password": NEW_STUDENT["password"]},
    )

    # Assert
    assert response.status_code == 200, response.text
    student = response.json()["user"]["student"]
    assert student["category"]["label"] == "B, C1"
    assert 58 <= student["days_left"] <= 60


async def test_duplicate_iin_is_refused(
    client: AsyncClient, db: AsyncSession
) -> None:
    # Arrange
    await create_staff(db, ADMIN_IIN, UserRole.ADMIN)
    headers = await sign_in(client, ADMIN_IIN)
    await client.post("/api/v1/students", headers=headers, json=NEW_STUDENT)

    # Act
    response = await client.post("/api/v1/students", headers=headers, json=NEW_STUDENT)

    # Assert
    assert response.status_code == 409
    assert response.json()["error"] == "Пользователь с таким ИИН уже существует"


async def test_manager_may_edit_a_student_but_not_delete_one(
    client: AsyncClient, db: AsyncSession
) -> None:
    # Arrange
    await create_staff(db, MANAGER_IIN, UserRole.MANAGER)
    headers = await sign_in(client, MANAGER_IIN)
    student_id = (
        await client.post("/api/v1/students", headers=headers, json=NEW_STUDENT)
    ) and (await client.get("/api/v1/students", headers=headers)).json()["items"][0][
        "id"
    ]

    # Act
    edited = await client.patch(
        f"/api/v1/students/{student_id}",
        headers=headers,
        json={"name": "Нурлан", "extend_days": 30},
    )
    deleted = await client.delete(f"/api/v1/students/{student_id}", headers=headers)

    # Assert
    assert edited.status_code == 200, edited.text
    assert edited.json()["name"] == "Нурлан"
    assert edited.json()["days_left"] >= 89
    assert deleted.status_code == 403
    assert deleted.json()["error"] == "Доступно только администратору"


async def test_admin_may_delete_a_student(
    client: AsyncClient, db: AsyncSession
) -> None:
    # Arrange
    await create_staff(db, ADMIN_IIN, UserRole.ADMIN)
    headers = await sign_in(client, ADMIN_IIN)
    await client.post("/api/v1/students", headers=headers, json=NEW_STUDENT)
    student_id = (await client.get("/api/v1/students", headers=headers)).json()[
        "items"
    ][0]["id"]

    # Act
    response = await client.delete(
        f"/api/v1/students/{student_id}", headers=headers
    )

    # Assert
    assert response.status_code == 200
    remaining = await client.get("/api/v1/students", headers=headers)
    assert remaining.json()["total"] == 0


async def test_student_cannot_reach_the_staff_area(
    client: AsyncClient, db: AsyncSession
) -> None:
    # Arrange
    await create_student(db, STUDENT_IIN)
    headers = await sign_in(client, STUDENT_IIN)

    # Act
    students = await client.get("/api/v1/students", headers=headers)
    managers = await client.get("/api/v1/managers", headers=headers)

    # Assert
    assert students.status_code == 403
    assert managers.status_code == 403


async def test_status_and_category_options_are_labelled_in_russian(
    client: AsyncClient, db: AsyncSession
) -> None:
    # Arrange
    await create_staff(db, ADMIN_IIN, UserRole.ADMIN)
    headers = await sign_in(client, ADMIN_IIN)

    # Act
    response = await client.get("/api/v1/students/options", headers=headers)

    # Assert
    options = response.json()
    assert {o["value"] for o in options["categories"]} == {"B", "B_C1"}
    assert "Активный" in {o["label"] for o in options["statuses"]}
    assert "Доступ истёк" in {o["label"] for o in options["statuses"]}


async def test_suspending_a_student_blocks_the_next_sign_in(
    client: AsyncClient, db: AsyncSession
) -> None:
    # Arrange
    await create_staff(db, ADMIN_IIN, UserRole.ADMIN)
    headers = await sign_in(client, ADMIN_IIN)
    await client.post("/api/v1/students", headers=headers, json=NEW_STUDENT)
    student_id = (await client.get("/api/v1/students", headers=headers)).json()[
        "items"
    ][0]["id"]

    # Act
    await client.patch(
        f"/api/v1/students/{student_id}",
        headers=headers,
        json={"status": "suspended"},
    )
    response = await client.post(
        "/api/v1/auth/login",
        json={"iin": NEW_STUDENT["iin"], "password": NEW_STUDENT["password"]},
    )

    # Assert
    assert response.status_code == 403
    assert "Приостановлен" in response.json()["error"]
