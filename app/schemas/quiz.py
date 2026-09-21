"""Schemas for running and reviewing a quiz session.

The session response is what makes a page reload lossless: it carries the whole
question set, the answers already given, and where the student left off.
"""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field, field_validator

from app.enums.language import Language
from app.enums.quiz import QuizMode
from app.schemas.common import LabeledValue
from app.schemas.content import QuestionRead


#: Ceiling on a custom selection. The catalogue holds far fewer topics than
#: this, so a longer list is a malformed request rather than a real choice.
MAX_CUSTOM_TOPICS = 100


class QuizStartRequest(BaseModel):
    """Begin a run.

    `topic_id` is required in TOPIC mode, `topic_ids` in CUSTOM mode; every
    other mode ignores both.
    """

    mode: QuizMode
    topic_id: int | None = None
    #: Topics the student ticked for a CUSTOM run.
    topic_ids: list[int] = Field(
        default_factory=list, max_length=MAX_CUSTOM_TOPICS
    )
    language: Language = Language.RU

    @field_validator("topic_ids")
    @classmethod
    def _drop_repeats(cls, value: list[int]) -> list[int]:
        """Deduplicate while keeping order.

        A repeated id would otherwise widen that topic's share of the draw,
        which is not what ticking a box twice in a stale client should mean.
        """
        return list(dict.fromkeys(value))


class AnswerRequest(BaseModel):
    """Record the student's choice for one question of the session."""

    question_id: int
    answer_id: int


class ItemState(BaseModel):
    """One slot of the session, as the navigation strip needs it.

    `is_correct` drives the colour of the numbered chip: green when right, red
    when wrong, neutral while unanswered.
    """

    position: int
    question_id: int
    is_answered: bool
    is_correct: bool | None = None
    answer_id: int | None = None


class AnswerResult(BaseModel):
    """What comes back after answering.

    In the exam these stay null: the run records the answer and moves on, the
    same way the real test does. Every other mode fills them in at once.
    """

    is_correct: bool | None = None
    correct_answer_id: int | None = None
    explanation: str | None = None
    explanation_video_url: str | None = None
    can_finish: bool
    answered_count: int
    #: False in the exam while it is still running.
    reveals_answer: bool = True


class SessionRead(BaseModel):
    """Everything needed to render — or restore — a running session."""

    id: int
    mode: LabeledValue
    status: LabeledValue
    language: Language
    topic_id: int | None
    title: str
    started_at: datetime
    total_questions: int
    answered_count: int
    correct_count: int
    can_finish: bool
    min_answers_to_finish: int
    #: Allotted time for timed modes; None when the run is untimed.
    time_limit_seconds: int | None = None
    #: Time remaining, so a reload restores the clock rather than restarting it.
    seconds_left: int | None = None
    #: Slot to open on load: the first unanswered one, else the last.
    current_position: int = Field(ge=0)
    #: False while an exam is running: the interface must not colour answers
    #: right or wrong, only mark them as answered.
    reveals_answers: bool = True
    items: list[ItemState]
    questions: list[QuestionRead]


class QuestionReview(BaseModel):
    """One question of a finished run, right or wrong.

    The result screen lists every question, not only the failed ones, so the
    student can see where they were right as well as where they slipped.
    """

    position: int
    question_id: int
    question_text: str
    given_answer_text: str | None
    correct_answer_text: str
    is_correct: bool
    is_answered: bool


#: Kept as an alias: the mistakes list is the failed subset of the review.
MistakeReview = QuestionReview


class SessionResult(BaseModel):
    """Outcome of a finished session."""

    id: int
    mode: LabeledValue
    title: str
    total_questions: int
    answered_count: int
    correct_count: int
    score_percent: int
    is_passed: bool
    time_seconds: int | None
    finished_at: datetime | None
    #: Every question of the run, in order.
    review: list[QuestionReview]
    #: The failed subset, for the "работа над ошибками" summary.
    mistakes: list[QuestionReview]


class ResultBrief(BaseModel):
    """A past attempt, listed in the student's history."""

    id: int
    mode: LabeledValue
    title: str
    total_questions: int
    answered_count: int
    correct_count: int
    score_percent: int
    is_passed: bool
    time_seconds: int | None
    finished_at: datetime | None
