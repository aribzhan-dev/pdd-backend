"""Test fixtures: an in-memory database and an authenticated HTTP client.

Tests run against SQLite rather than PostgreSQL so they need no server. The
models avoid native enums and other dialect-specific features precisely so the
same schema builds on both.
"""
from __future__ import annotations

import os
from collections.abc import AsyncGenerator
from datetime import UTC, datetime, timedelta

os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://pdd:pdd@localhost/pdd")
os.environ.setdefault("SECRET_KEY", "test-secret-key-that-is-long-enough-000000")

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from app.core.db import get_db
from app.core.security import hash_password
from app.enums.category import DrivingCategory
from app.enums.role import UserRole
from app.enums.student_status import StudentStatus
from app.main import app
from app.repositories.user import UserRepository
from app.models import (
    Answer,
    Base,
    MediaAsset,
    MediaKind,
    Question,
    StudentProfile,
    Topic,
    User,
)

#: Enough questions that a 40-question exam and early finishing are testable.
QUESTIONS_PER_TOPIC = 45

TEST_PASSWORD = "test-password-123"


@pytest.fixture
async def session_factory() -> AsyncGenerator[async_sessionmaker[AsyncSession], None]:
    """A fresh in-memory schema per test, shared across connections."""
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    yield factory
    await engine.dispose()


@pytest.fixture(autouse=True)
def reset_login_limiter() -> None:
    """Clear the process-wide sign-in limiter so tests never leak lock state."""
    from app.core.rate_limit import get_login_limiter

    get_login_limiter()._buckets.clear()


@pytest.fixture
async def db(
    session_factory: async_sessionmaker[AsyncSession],
) -> AsyncGenerator[AsyncSession, None]:
    """A session for arranging fixtures directly."""
    async with session_factory() as session:
        yield session


@pytest.fixture
async def client(
    session_factory: async_sessionmaker[AsyncSession],
) -> AsyncGenerator[AsyncClient, None]:
    """HTTP client wired to the app, with the database dependency overridden."""

    async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as http:
        yield http
    app.dependency_overrides.clear()


# --- Fixture builders -------------------------------------------------------


def make_user(iin: str, role: UserRole, **overrides: object) -> User:
    """A user row with sensible defaults for tests."""
    defaults = {
        "iin": iin,
        "password_hash": hash_password(TEST_PASSWORD),
        "name": "Test",
        "surname": role.value.capitalize(),
        "role": role,
    }
    return User(**{**defaults, **overrides})


async def create_student(
    db: AsyncSession,
    iin: str = "060422501511",
    *,
    access_days: int = 30,
    status: StudentStatus = StudentStatus.ACTIVE,
    category: DrivingCategory = DrivingCategory.B,
) -> User:
    """A student account with an access window."""
    user = make_user(iin, UserRole.STUDENT)
    db.add(user)
    await db.flush()
    now = datetime.now(UTC)
    db.add(
        StudentProfile(
            user_id=user.id,
            category=category,
            status=status,
            access_starts_at=now - timedelta(days=1),
            access_expires_at=now + timedelta(days=access_days),
        )
    )
    await db.commit()
    # Re-read through the repository so the profile relationship is loaded and
    # the test can touch it without triggering IO outside the async context.
    loaded = await UserRepository(db).get_by_id(user.id)
    assert loaded is not None
    return loaded


async def create_staff(db: AsyncSession, iin: str, role: UserRole) -> User:
    """An admin or manager account."""
    user = make_user(iin, role)
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


async def create_content(db: AsyncSession) -> Topic:
    """One topic with questions, three answers each, sharing one video.

    The shared media asset mirrors production, where a single placeholder clip
    is referenced by hundreds of questions.
    """
    shared_video = MediaAsset(
        sha256="a" * 64,
        rel_path="videos/situations/shared.mp4",
        kind=MediaKind.SITUATION,
        byte_size=1024,
        duplicate_count=QUESTIONS_PER_TOPIC,
    )
    db.add(shared_video)
    await db.flush()

    topic = Topic(number=1, title_ru="Общие положения", title_kz="Жалпы ережелер")
    db.add(topic)
    await db.flush()

    for index in range(QUESTIONS_PER_TOPIC):
        question = Question(
            topic_id=topic.id,
            text_ru=f"Вопрос {index}",
            text_kz=f"Сұрақ {index}",
            explanation_ru=f"Пояснение {index}",
            content_hash=f"hash-{index}",
            situation_video_id=shared_video.id,
            order=index,
        )
        db.add(question)
        await db.flush()
        for choice in range(3):
            db.add(
                Answer(
                    question_id=question.id,
                    text_ru=f"Ответ {choice}",
                    is_correct=choice == 0,
                    order=choice,
                )
            )
    await db.commit()
    return topic


async def create_extra_topic(
    db: AsyncSession, *, number: int, question_count: int
) -> Topic:
    """A second, media-free topic for tests that need more than one.

    `create_content` builds the rich topic the media and localisation tests
    rely on. This one exists only to be picked alongside it, so it carries
    just enough to be answerable and its question texts name their topic,
    which is how a draw can be proved to have stayed inside the selection.
    """
    topic = Topic(
        number=number,
        title_ru=f"Тема {number}",
        title_kz=f"Тақырып {number}",
    )
    db.add(topic)
    await db.flush()

    for index in range(question_count):
        question = Question(
            topic_id=topic.id,
            text_ru=f"Тема {number}, вопрос {index}",
            text_kz=f"Тақырып {number}, сұрақ {index}",
            content_hash=f"hash-{number}-{index}",
            order=index,
        )
        db.add(question)
        await db.flush()
        for choice in range(3):
            db.add(
                Answer(
                    question_id=question.id,
                    text_ru=f"Ответ {choice}",
                    is_correct=choice == 0,
                    order=choice,
                )
            )
    await db.commit()
    return topic


async def sign_in(client: AsyncClient, iin: str) -> dict[str, str]:
    """Log in and return the Authorization header for later calls."""
    response = await client.post(
        "/api/v1/auth/login", json={"iin": iin, "password": TEST_PASSWORD}
    )
    assert response.status_code == 200, response.text
    token = response.json()["tokens"]["access_token"]
    return {"Authorization": f"Bearer {token}"}
