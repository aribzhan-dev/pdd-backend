"""Schemas for localised catalogue content: topics, questions, answers, videos.

The service layer resolves `*_ru` / `*_kz` against the requested language
before serialising, so the client receives plain fields.
"""
from __future__ import annotations

from pydantic import BaseModel


class MediaRead(BaseModel):
    """A media file as the client should request it."""

    url: str
    kind: str
    byte_size: int


class AnswerRead(BaseModel):
    """An answer option. `is_correct` is withheld until the student answers."""

    id: int
    text: str
    is_correct: bool | None = None


class QuestionRead(BaseModel):
    """A question resolved into one language."""

    id: int
    text: str
    explanation: str | None = None
    image: MediaRead | None = None
    situation_video: MediaRead | None = None
    explanation_video: MediaRead | None = None
    is_exam_only: bool
    answers: list[AnswerRead]


class TopicBrief(BaseModel):
    """Catalogue tile for one topic."""

    id: int
    number: int
    title: str
    question_count: int
    #: How many parts the topic is offered in. 1 means it is run in one go.
    part_count: int = 1
    best_percent: int | None = None


class TopicDetail(TopicBrief):
    """A topic together with its questions."""

    description: str | None = None
    questions: list[QuestionRead]


class VideoRead(BaseModel):
    """A lesson video."""

    id: int
    title: str
    youtube_url: str
    order: int
