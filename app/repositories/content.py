"""Database access for catalogue content: topics, questions and videos."""
from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from app.models.question import Question
from app.models.topic import Topic
from app.models.video import Video
from app.repositories.base import BaseRepository

#: Eager-loads every media relation a question can render.
_QUESTION_MEDIA = (
    selectinload(Question.image),
    selectinload(Question.situation_video),
    selectinload(Question.explanation_video_ru),
    selectinload(Question.explanation_video_kz),
)


class ContentRepository(BaseRepository):
    """Read-side queries for the learning catalogue."""

    async def list_topics(self) -> list[Topic]:
        """Active topics in curriculum order."""
        rows = await self.session.scalars(
            select(Topic).where(Topic.is_active.is_(True)).order_by(Topic.number)
        )
        return list(rows)

    async def count_questions_by_topic(self) -> dict[int, int]:
        """Question totals keyed by topic id, for the catalogue tiles."""
        rows = await self.session.execute(
            select(Question.topic_id, func.count(Question.id)).group_by(
                Question.topic_id
            )
        )
        return {topic_id: count for topic_id, count in rows}

    async def get_topic(self, topic_id: int) -> Topic | None:
        """One topic without its questions."""
        return await self.session.get(Topic, topic_id)

    async def list_questions_by_topic(self, topic_id: int) -> list[Question]:
        """Every question of a topic, media eagerly loaded."""
        rows = await self.session.scalars(
            select(Question)
            .where(Question.topic_id == topic_id)
            .options(*_QUESTION_MEDIA)
            .order_by(Question.order, Question.id)
        )
        return list(rows)

    async def get_questions(self, question_ids: list[int]) -> list[Question]:
        """Load a specific set of questions, media eagerly loaded."""
        if not question_ids:
            return []
        rows = await self.session.scalars(
            select(Question)
            .where(Question.id.in_(question_ids))
            .options(*_QUESTION_MEDIA)
        )
        return list(rows)

    async def sample_random_questions(self, count: int) -> list[Question]:
        """Pick questions at random for an exam run."""
        rows = await self.session.scalars(
            select(Question)
            .options(*_QUESTION_MEDIA)
            .order_by(func.random())
            .limit(count)
        )
        return list(rows)

    async def list_videos(self) -> list[Video]:
        """Active lesson videos in display order."""
        rows = await self.session.scalars(
            select(Video).where(Video.is_active.is_(True)).order_by(Video.order)
        )
        return list(rows)
