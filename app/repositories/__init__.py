"""Repositories — the only layer that talks SQL."""
from app.repositories.base import BaseRepository
from app.repositories.content import ContentRepository
from app.repositories.quiz import QuizRepository
from app.repositories.user import UserRepository

__all__ = [
    "BaseRepository",
    "ContentRepository",
    "QuizRepository",
    "UserRepository",
]
