"""Model registry — imported by Alembic so autogenerate sees every table."""
from app.models.answer import Answer
from app.models.base import Base, TimestampMixin
from app.models.media_asset import MediaAsset, MediaKind
from app.models.mistake import Mistake
from app.models.question import ContentSource, Question
from app.models.quiz import (
    MIN_ANSWERS_TO_FINISH,
    PASS_RATIO,
    QuizItem,
    QuizSession,
)
from app.models.student_profile import StudentProfile
from app.models.topic import Topic
from app.models.user import User
from app.models.video import Video

__all__ = [
    "Answer",
    "Base",
    "ContentSource",
    "MIN_ANSWERS_TO_FINISH",
    "MediaAsset",
    "MediaKind",
    "Mistake",
    "PASS_RATIO",
    "Question",
    "QuizItem",
    "QuizSession",
    "StudentProfile",
    "TimestampMixin",
    "Topic",
    "User",
    "Video",
]
