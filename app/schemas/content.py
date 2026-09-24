"""Schemas for localised catalogue content: topics, questions, answers, videos.

The service layer resolves `*_ru` / `*_kz` against the requested language
before serialising, so the client receives plain fields.
"""
from __future__ import annotations

from pydantic import BaseModel, Field


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


class TopicPartBrief(BaseModel):
    """One sitting-sized stretch of a long topic, with its own score."""

    #: 1-based, and what a run passes back as `part`.
    index: int
    question_count: int
    best_percent: int | None = None


class TopicBrief(BaseModel):
    """Catalogue tile for one topic."""

    id: int
    number: int
    title: str
    question_count: int
    #: Empty when the topic is short enough to be run in one go.
    parts: list[TopicPartBrief] = Field(default_factory=list)
    #: Across the whole chapter: parts count for what they hold, so one part
    #: of four at 100% shows as a quarter.
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
