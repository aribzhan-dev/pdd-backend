"""Database access for quiz sessions, results and the mistake collection."""
from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from app.core.time import utc_now
from app.enums.quiz import QuizStatus
from app.models.mistake import Mistake
from app.models.question import Question
from app.models.quiz import QuizItem, QuizSession
from app.repositories.base import BaseRepository

#: Loads a session together with its items and their questions and media.
_SESSION_GRAPH = selectinload(QuizSession.items).selectinload(QuizItem.question)


class QuizRepository(BaseRepository):
    """Queries over sessions, their items and per-student mistakes."""

    async def get_session(self, session_id: int) -> QuizSession | None:
        """Load a session with everything needed to render it."""
        stmt = (
            select(QuizSession)
            .where(QuizSession.id == session_id)
            .options(
                _SESSION_GRAPH.selectinload(Question.answers),
                _SESSION_GRAPH.selectinload(Question.image),
                _SESSION_GRAPH.selectinload(Question.situation_video),
                _SESSION_GRAPH.selectinload(Question.explanation_video_ru),
                _SESSION_GRAPH.selectinload(Question.explanation_video_kz),
            )
        )
        return await self.session.scalar(stmt)

    async def find_active_session(self, user_id: int) -> QuizSession | None:
        """The student's unfinished session, if one exists.

        This is what makes a reload lossless: the client asks for it on load
        instead of starting over.
        """
        stmt = (
            select(QuizSession.id)
            .where(
                QuizSession.user_id == user_id,
                QuizSession.status == QuizStatus.IN_PROGRESS,
            )
            .order_by(QuizSession.started_at.desc())
            .limit(1)
        )
        session_id = await self.session.scalar(stmt)
        return await self.get_session(session_id) if session_id else None

    async def list_finished(
        self, user_id: int, *, page: int = 1, limit: int = 20
    ) -> tuple[list[QuizSession], int]:
        """One page of the student's completed attempts, newest first."""
        base = select(QuizSession).where(
            QuizSession.user_id == user_id,
            QuizSession.status == QuizStatus.FINISHED,
        )
        total = await self.session.scalar(
            select(func.count()).select_from(base.subquery())
        )
        rows = await self.session.scalars(
            base.options(selectinload(QuizSession.items))
            .order_by(QuizSession.finished_at.desc())
            .offset((page - 1) * limit)
            .limit(limit)
        )
        return list(rows), int(total or 0)

    async def best_percent_by_topic_part(
        self, user_id: int
    ) -> dict[tuple[int, int | None], int]:
        """Best score per topic and part, used for the catalogue badges.

        The key's second half is the part number, or None for a run that took
        the topic whole — which every run was before topics were split, so old
        results keep a place of their own rather than being attributed to a
        part they never covered.

        The score of one session is computed in a subquery first: taking the
        maximum of a count in a single query would nest one aggregate inside
        another, which PostgreSQL rejects outright.
        """
        per_session = (
            select(
                QuizSession.topic_id.label("topic_id"),
                QuizSession.topic_part.label("topic_part"),
                (
                    100.0
                    * func.count(QuizItem.id).filter(QuizItem.is_correct.is_(True))
                    / func.nullif(func.count(QuizItem.id), 0)
                ).label("percent"),
            )
            .join(QuizItem, QuizItem.session_id == QuizSession.id)
            .where(
                QuizSession.user_id == user_id,
                QuizSession.status == QuizStatus.FINISHED,
                QuizSession.topic_id.is_not(None),
            )
            .group_by(
                QuizSession.id, QuizSession.topic_id, QuizSession.topic_part
            )
            .subquery()
        )

        rows = await self.session.execute(
            select(
                per_session.c.topic_id,
                per_session.c.topic_part,
                func.max(per_session.c.percent),
            ).group_by(per_session.c.topic_id, per_session.c.topic_part)
        )
        return {
            (topic_id, topic_part): int(round(percent or 0))
            for topic_id, topic_part, percent in rows
            if topic_id is not None
        }

    def add_session(self, session: QuizSession) -> QuizSession:
        """Stage a new session; the caller commits."""
        self.session.add(session)
        return session

    # --- Mistake collection -------------------------------------------------

    async def list_mistake_question_ids(self, user_id: int) -> list[int]:
        """Questions the student is currently getting wrong."""
        rows = await self.session.scalars(
            select(Mistake.question_id)
            .where(Mistake.user_id == user_id)
            .order_by(Mistake.last_wrong_at.desc())
        )
        return list(rows)

    async def count_mistakes(self, user_id: int) -> int:
        """Size of the mistake collection."""
        return int(
            await self.session.scalar(
                select(func.count())
                .select_from(Mistake)
                .where(Mistake.user_id == user_id)
            )
            or 0
        )

    async def record_mistake(self, user_id: int, question_id: int) -> None:
        """Add the question to the collection, or bump its counter."""
        existing = await self.session.scalar(
            select(Mistake).where(
                Mistake.user_id == user_id, Mistake.question_id == question_id
            )
        )
        now = utc_now()
        if existing is None:
            self.session.add(
                Mistake(user_id=user_id, question_id=question_id, last_wrong_at=now)
            )
            return
        existing.wrong_count += 1
        existing.last_wrong_at = now

    async def clear_mistake(self, user_id: int, question_id: int) -> None:
        """Drop the question once it has been answered correctly."""
        existing = await self.session.scalar(
            select(Mistake).where(
                Mistake.user_id == user_id, Mistake.question_id == question_id
            )
        )
        if existing is not None:
            await self.session.delete(existing)
