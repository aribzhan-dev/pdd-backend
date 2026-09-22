"""Running a quiz: starting, answering, resuming and finishing.

Three requirements shape this service:
  * a reload must lose nothing — the session, its question order and every
    answer live in the database, so the client can always restore state;
  * the navigation strip must show which questions were right and which wrong,
    which `ItemState` carries;
  * a student may finish early once MIN_ANSWERS_TO_FINISH answers are in,
    without working through all forty questions.
"""
from __future__ import annotations

import random

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError, QuizStateError
from app.core.time import as_utc, utc_now
from app.enums.language import Language
from app.enums.quiz import QuizMode, QuizStatus
from app.models.answer import Answer
from app.models.question import Question
from app.models.quiz import MIN_ANSWERS_TO_FINISH, QuizItem, QuizSession
from app.repositories.content import ContentRepository
from app.repositories.quiz import QuizRepository
from app.schemas.common import Page
from app.schemas.quiz import (
    AnswerResult,
    ItemState,
    QuestionReview,
    ResultBrief,
    SessionRead,
    SessionResult,
)
from app.services.content import localize, media_url, serialize_question, topic_title
from app.services.labels import to_labeled

#: Number of questions drawn for an exam or a training run.
EXAM_QUESTION_COUNT = 40

#: The exam is timed like the real one; training has no clock.
EXAM_TIME_LIMIT_SECONDS = 40 * 60

#: A self-chosen topic set is capped at the same size as an exam — more than
#: forty questions in one sitting is a different exercise. Below the cap the
#: run simply holds every question the chosen topics have.
CUSTOM_QUESTION_LIMIT = EXAM_QUESTION_COUNT

#: Fallback headings when the run is not tied to a topic.
MODE_TITLES: dict[QuizMode, str] = {
    QuizMode.EXAM: "Экзамен",
    QuizMode.TRAINING: "Режим обучения",
    QuizMode.MISTAKES: "Работа над ошибками",
    QuizMode.CUSTOM: "Выбранные темы",
}

#: Modes that draw a random 40-question set rather than a fixed topic.
RANDOM_MODES = frozenset({QuizMode.EXAM, QuizMode.TRAINING})


class QuizService:
    """Everything behind the /quiz endpoints."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.quiz = QuizRepository(session)
        self.content = ContentRepository(session)

    # --- Starting and resuming ---------------------------------------------

    async def get_active(
        self, user_id: int, language: Language | None = None
    ) -> SessionRead | None:
        """The unfinished session to restore on page load, if any."""
        session = await self.quiz.find_active_session(user_id)
        if session is None:
            return None
        if session.is_out_of_time:
            await self._close(session)
            return None
        return await self._read(session, language)

    async def get_session(
        self, user_id: int, session_id: int, language: Language | None = None
    ) -> SessionRead:
        """Re-read one of the caller's sessions, answers included."""
        return await self._read(
            await self._owned_session(user_id, session_id), language
        )

    async def start(
        self,
        user_id: int,
        mode: QuizMode,
        language: Language,
        topic_id: int | None,
        topic_ids: list[int] | None = None,
    ) -> SessionRead:
        """Begin a run, replacing any session still open.

        Only one session is active at a time: starting a new one abandons the
        previous one rather than leaving two resumable runs behind.
        """
        questions = await self._pick_questions(
            user_id, mode, topic_id, topic_ids or []
        )
        if not questions:
            raise QuizStateError("Для этого режима нет доступных вопросов")

        await self._abandon_active(user_id)

        session = QuizSession(
            user_id=user_id,
            topic_id=topic_id if mode is QuizMode.TOPIC else None,
            mode=mode,
            language=language,
            status=QuizStatus.IN_PROGRESS,
            started_at=utc_now(),
            time_limit_seconds=(
                EXAM_TIME_LIMIT_SECONDS if mode is QuizMode.EXAM else None
            ),
        )
        session.items = [
            QuizItem(question_id=question.id, position=position)
            for position, question in enumerate(questions)
        ]
        self.quiz.add_session(session)
        await self.session.commit()

        restored = await self.quiz.get_session(session.id)
        return await self._read(restored)

    async def _pick_questions(
        self,
        user_id: int,
        mode: QuizMode,
        topic_id: int | None,
        topic_ids: list[int],
    ) -> list[Question]:
        """Choose the question set for the requested mode."""
        if mode is QuizMode.TOPIC:
            if topic_id is None:
                raise QuizStateError("Для режима темы нужно указать тему")
            questions = await self.content.list_questions_by_topic(topic_id)
            # The catalogue lists a topic in its authored order; running it is
            # a test, so the order is drawn fresh for every attempt.
            return _shuffled(questions)

        if mode is QuizMode.CUSTOM:
            if not topic_ids:
                raise QuizStateError("Выберите хотя бы одну тему")
            return await self.content.sample_questions_by_topics(
                topic_ids, CUSTOM_QUESTION_LIMIT
            )

        if mode in RANDOM_MODES:
            return await self.content.sample_random_questions(EXAM_QUESTION_COUNT)

        mistake_ids = await self.quiz.list_mistake_question_ids(user_id)
        return _shuffled(await self.content.get_questions(mistake_ids))

    async def _abandon_active(self, user_id: int) -> None:
        """Close any session left open, so exactly one is resumable."""
        active = await self.quiz.find_active_session(user_id)
        if active is None:
            return
        active.status = QuizStatus.FINISHED
        active.finished_at = utc_now()
        await self.session.flush()

    # --- Answering ----------------------------------------------------------

    async def answer(
        self,
        user_id: int,
        session_id: int,
        question_id: int,
        answer_id: int,
        language: Language | None = None,
    ) -> AnswerResult:
        """Record one answer and return the feedback for it.

        Answering the same question twice is refused, so a stale tab cannot
        overwrite a result that already counted.
        """
        session = await self._owned_session(user_id, session_id)
        if session.status is not QuizStatus.IN_PROGRESS:
            raise QuizStateError("Сессия уже завершена")
        if session.is_out_of_time:
            await self._close(session)
            raise QuizStateError("Время вышло — тест завершён")

        item = next((i for i in session.items if i.question_id == question_id), None)
        if item is None:
            raise NotFoundError("Вопрос не входит в эту сессию")
        if item.is_answered:
            raise QuizStateError("На этот вопрос уже дан ответ")

        question = item.question
        chosen = next((a for a in question.answers if a.id == answer_id), None)
        if chosen is None:
            raise NotFoundError("Вариант ответа не найден")
        correct = _correct_answer(question)

        item.answer_id = chosen.id
        item.is_correct = chosen.is_correct
        item.answered_at = utc_now()
        reveals = session.mode.reveals_answers_immediately

        if chosen.is_correct:
            await self.quiz.clear_mistake(user_id, question_id)
        else:
            await self.quiz.record_mistake(user_id, question_id)
        await self.session.commit()

        language = language or session.language
        explanation_video = (
            question.explanation_video_kz or question.explanation_video_ru
            if language is Language.KZ
            else question.explanation_video_ru
        )
        video = media_url(explanation_video)
        return AnswerResult(
            is_correct=chosen.is_correct if reveals else None,
            correct_answer_id=correct.id if reveals else None,
            explanation=(
                localize(question.explanation_ru, question.explanation_kz, language)
                if reveals
                else None
            ),
            explanation_video_url=video.url if (reveals and video) else None,
            can_finish=session.can_finish,
            answered_count=session.answered_count,
            reveals_answer=reveals,
        )

    # --- Finishing ----------------------------------------------------------

    async def finish(
        self, user_id: int, session_id: int, language: Language | None = None
    ) -> SessionResult:
        """Close a session early or at the end and return its result.

        Unanswered questions count as wrong, so finishing after ten answers of
        forty scores against all forty.
        """
        session = await self._owned_session(user_id, session_id)
        if session.status is QuizStatus.FINISHED:
            return _build_result(session, language)
        if not session.can_finish:
            raise QuizStateError(
                f"Ответьте минимум на {MIN_ANSWERS_TO_FINISH} вопросов, "
                "чтобы завершить тест"
            )

        await self._close(session)
        return _build_result(session, language)

    async def get_result(
        self, user_id: int, session_id: int, language: Language | None = None
    ) -> SessionResult:
        """Re-read a finished session's result."""
        session = await self._owned_session(user_id, session_id)
        if session.status is not QuizStatus.FINISHED:
            raise QuizStateError("Сессия ещё не завершена")
        return _build_result(session, language)

    async def list_history(
        self, user_id: int, *, page: int, limit: int
    ) -> Page[ResultBrief]:
        """The student's past attempts, newest first."""
        sessions, total = await self.quiz.list_finished(
            user_id, page=page, limit=limit
        )
        return Page(
            items=[
                ResultBrief(
                    id=item.id,
                    mode=to_labeled(item.mode),
                    title=MODE_TITLES.get(item.mode, item.mode.label),
                    total_questions=item.total_questions,
                    answered_count=item.answered_count,
                    correct_count=item.correct_count,
                    score_percent=item.score_percent,
                    is_passed=item.is_passed,
                    time_seconds=item.time_seconds,
                    finished_at=item.finished_at,
                )
                for item in sessions
            ],
            total=total,
            page=page,
            limit=limit,
        )

    # --- Internals ----------------------------------------------------------

    async def _close(self, session: QuizSession) -> None:
        """Mark a run finished and record how long it took."""
        now = utc_now()
        session.status = QuizStatus.FINISHED
        session.finished_at = now
        session.time_seconds = int((now - as_utc(session.started_at)).total_seconds())
        await self.session.commit()

    async def _owned_session(self, user_id: int, session_id: int) -> QuizSession:
        """Load a session and confirm it belongs to the caller."""
        session = await self.quiz.get_session(session_id)
        if session is None or session.user_id != user_id:
            raise NotFoundError("Сессия не найдена")
        return session

    async def _read(
        self, session: QuizSession | None, language: Language | None = None
    ) -> SessionRead:
        """Serialise a session, revealing answers only where already given.

        `language` overrides the one the session was started with, so the
        switcher re-renders the same questions rather than being ignored.
        """
        if session is None:
            raise NotFoundError("Сессия не найдена")

        language = language or session.language
        topic = (
            await self.content.get_topic(session.topic_id)
            if session.topic_id
            else None
        )
        title = (
            topic_title(topic, language)
            if topic
            else MODE_TITLES.get(session.mode, session.mode.label)
        )

        # A finished exam may be reviewed in full; a running one may not.
        reveals = (
            session.mode.reveals_answers_immediately
            or session.status is QuizStatus.FINISHED
        )

        return SessionRead(
            id=session.id,
            mode=to_labeled(session.mode),
            status=to_labeled(session.status),
            language=language,
            topic_id=session.topic_id,
            title=title,
            started_at=session.started_at,
            total_questions=session.total_questions,
            answered_count=session.answered_count,
            correct_count=session.correct_count,
            can_finish=session.can_finish,
            min_answers_to_finish=MIN_ANSWERS_TO_FINISH,
            time_limit_seconds=session.time_limit_seconds,
            seconds_left=session.seconds_left,
            current_position=_resume_position(session),
            reveals_answers=reveals,
            items=[_to_item_state(item, reveals) for item in session.items],
            questions=[
                serialize_question(
                    item.question,
                    language,
                    reveal_answers=item.is_answered and reveals,
                    #: The slot id keeps each question's option order fixed for
                    #: this session while differing between sessions.
                    answer_seed=item.id,
                )
                for item in session.items
            ],
        )


def _shuffled(questions: list[Question]) -> list[Question]:
    """A new list in random order, leaving the caller's list untouched."""
    return random.sample(questions, len(questions))


def _correct_answer(question: Question) -> Answer:
    """The correct option. Imported content always carries exactly one."""
    correct = next((a for a in question.answers if a.is_correct), None)
    if correct is None:
        raise QuizStateError(f"У вопроса {question.id} нет правильного ответа")
    return correct


def _resume_position(session: QuizSession) -> int:
    """Where to reopen a session: the first unanswered slot, else the last."""
    for item in session.items:
        if not item.is_answered:
            return item.position
    return max(0, session.total_questions - 1)


def _to_item_state(item: QuizItem, reveals: bool) -> ItemState:
    """One chip in the navigation strip.

    `is_correct` stays null while an exam is running, so the strip can only
    show whether a question was answered — never whether it was right.
    """
    return ItemState(
        position=item.position,
        question_id=item.question_id,
        is_answered=item.is_answered,
        is_correct=item.is_correct if (item.is_answered and reveals) else None,
        answer_id=item.answer_id,
    )


def _build_result(
    session: QuizSession, language: Language | None = None
) -> SessionResult:
    """Score card plus the list of questions that went wrong."""
    language = language or session.language
    review = [
        QuestionReview(
            position=item.position,
            question_id=item.question_id,
            question_text=localize(
                item.question.text_ru, item.question.text_kz, language
            )
            or "",
            given_answer_text=_answer_text(item, language),
            correct_answer_text=localize(
                _correct_answer(item.question).text_ru,
                _correct_answer(item.question).text_kz,
                language,
            )
            or "",
            is_correct=item.is_correct,
            is_answered=item.is_answered,
        )
        for item in session.items
    ]
    mistakes = [entry for entry in review if not entry.is_correct]
    return SessionResult(
        id=session.id,
        mode=to_labeled(session.mode),
        title=MODE_TITLES.get(session.mode, session.mode.label),
        total_questions=session.total_questions,
        answered_count=session.answered_count,
        correct_count=session.correct_count,
        score_percent=session.score_percent,
        is_passed=session.is_passed,
        time_seconds=session.time_seconds,
        finished_at=session.finished_at,
        review=review,
        mistakes=mistakes,
    )


def _answer_text(item: QuizItem, language: Language) -> str | None:
    """Text of the option the student picked, or None if skipped."""
    if item.answer_id is None:
        return None
    chosen = next(
        (a for a in item.question.answers if a.id == item.answer_id), None
    )
    if chosen is None:
        return None
    return localize(chosen.text_ru, chosen.text_kz, language)
