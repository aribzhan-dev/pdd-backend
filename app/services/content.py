"""Catalogue reads, resolved into one language.

Localised columns come in `*_ru` / `*_kz` pairs. Russian is the primary text
and the fallback whenever a Kazakh translation is missing, so the client never
receives an empty string.
"""
from __future__ import annotations

import math
import random

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.exceptions import NotFoundError
from app.enums.language import Language
from app.models.answer import Answer
from app.models.media_asset import MediaAsset
from app.models.question import Question
from app.models.topic import Topic
from app.repositories.content import ContentRepository
from app.repositories.quiz import QuizRepository
from app.services.media_url import build_media_url
from app.schemas.content import (
    AnswerRead,
    MediaRead,
    QuestionRead,
    TopicBrief,
    TopicDetail,
    VideoRead,
)

settings = get_settings()

#: A topic longer than this is offered in parts, so that one sitting stays the
#: size of an exam however large the chapter is. Parts are filled to this size
#: in order and the last one takes what is left.
TOPIC_PART_SIZE = 40


def part_count(question_count: int) -> int:
    """How many parts a topic of this size is offered in; 1 means undivided."""
    if question_count <= TOPIC_PART_SIZE:
        return 1
    return math.ceil(question_count / TOPIC_PART_SIZE)


def part_slice(part: int) -> slice:
    """Which stretch of a topic's questions belongs to `part` (1-based)."""
    start = (part - 1) * TOPIC_PART_SIZE
    return slice(start, start + TOPIC_PART_SIZE)


def localize(ru: str | None, kz: str | None, language: Language) -> str | None:
    """Pick the text for a language, falling back to Russian."""
    if language is Language.KZ:
        return kz or ru
    return ru


def media_url(asset: MediaAsset | None) -> MediaRead | None:
    """Build the client-facing URL for a deduplicated asset.

    Many questions share one asset, so many questions legitimately return the
    same URL — that is the point of the deduplication.

    Whether the URL points at this server or at the platform the clip came
    from is a deployment setting; the escaping differs between the two, which
    `build_media_url` handles.
    """
    if asset is None:
        return None
    return MediaRead(
        url=build_media_url(
            asset.rel_path,
            serve_local=settings.MEDIA_SERVE_LOCAL,
            prefix=settings.MEDIA_URL_PREFIX,
            otan_origin=settings.MEDIA_ORIGIN_OTAN,
            pddtest_origin=settings.MEDIA_ORIGIN_PDDTEST,
        ),
        kind=asset.kind.value,
        byte_size=asset.byte_size,
    )


def shuffled_answers(question: Question, seed: int) -> list[Answer]:
    """The question's options in a stable, seeded random order.

    Two things are needed at once: the correct option must not sit in the same
    place every time, and the order must not move under the student. Seeding
    from the session's own slot id gives both — the order is drawn once per
    slot, so a reload, a revisit from the navigation strip or the result screen
    all show the options exactly where they were.
    """
    return random.Random(seed).sample(question.answers, len(question.answers))


def serialize_question(
    question: Question,
    language: Language,
    *,
    reveal_answers: bool,
    answer_seed: int | None = None,
) -> QuestionRead:
    """Render a question in one language.

    `reveal_answers` stays False while the question is unanswered so the
    correct option is not sitting in the network response. `answer_seed`
    shuffles the options; without it they keep their authored order, which is
    what the catalogue listing wants.
    """
    answers = (
        shuffled_answers(question, answer_seed)
        if answer_seed is not None
        else list(question.answers)
    )
    explanation_video = (
        question.explanation_video_kz or question.explanation_video_ru
        if language is Language.KZ
        else question.explanation_video_ru
    )
    return QuestionRead(
        id=question.id,
        text=localize(question.text_ru, question.text_kz, language) or "",
        explanation=(
            localize(question.explanation_ru, question.explanation_kz, language)
            if reveal_answers
            else None
        ),
        image=media_url(question.image),
        situation_video=media_url(question.situation_video),
        explanation_video=media_url(explanation_video) if reveal_answers else None,
        is_exam_only=question.is_exam_only,
        answers=[
            AnswerRead(
                id=answer.id,
                text=localize(answer.text_ru, answer.text_kz, language) or "",
                is_correct=answer.is_correct if reveal_answers else None,
            )
            for answer in answers
        ],
    )


class ContentService:
    """Read-side of the learning catalogue."""

    def __init__(self, session: AsyncSession) -> None:
        self.content = ContentRepository(session)
        self.quiz = QuizRepository(session)

    async def list_topics(self, user_id: int, language: Language) -> list[TopicBrief]:
        """Catalogue tiles, each carrying the student's best score so far."""
        topics = await self.content.list_topics()
        counts = await self.content.count_questions_by_topic()
        best = await self.quiz.best_percent_by_topic(user_id)
        return [
            TopicBrief(
                id=topic.id,
                number=topic.number,
                title=localize(topic.title_ru, topic.title_kz, language) or "",
                question_count=counts.get(topic.id, 0),
                part_count=part_count(counts.get(topic.id, 0)),
                best_percent=best.get(topic.id),
            )
            for topic in topics
        ]

    async def get_topic(
        self, topic_id: int, user_id: int, language: Language
    ) -> TopicDetail:
        """One topic with all of its questions, answers hidden."""
        topic = await self.content.get_topic(topic_id)
        if topic is None or not topic.is_active:
            raise NotFoundError("Тема не найдена")

        questions = await self.content.list_questions_by_topic(topic_id)
        best = await self.quiz.best_percent_by_topic(user_id)
        return TopicDetail(
            id=topic.id,
            number=topic.number,
            title=localize(topic.title_ru, topic.title_kz, language) or "",
            description=localize(
                topic.description_ru, topic.description_kz, language
            ),
            question_count=len(questions),
            best_percent=best.get(topic.id),
            questions=[
                serialize_question(question, language, reveal_answers=False)
                for question in questions
            ],
        )

    async def list_videos(self, language: Language) -> list[VideoRead]:
        """Lesson videos in display order."""
        videos = await self.content.list_videos()
        return [
            VideoRead(
                id=video.id,
                title=localize(video.title_ru, video.title_kz, language) or "",
                youtube_url=video.youtube_url,
                order=video.order,
            )
            for video in videos
        ]


def topic_title(topic: Topic | None, language: Language) -> str:
    """Session heading for a topic run."""
    if topic is None:
        return ""
    title = localize(topic.title_ru, topic.title_kz, language) or ""
    return f"{topic.number}. {title}"
