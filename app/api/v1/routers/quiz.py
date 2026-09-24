from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query, Response, status

from app.api.deps import DbSession, LanguageDep, StudentDep
from app.schemas.common import Page
from app.schemas.quiz import (
    AnswerRequest,
    AnswerResult,
    QuizStartRequest,
    ResultBrief,
    SessionRead,
    SessionResult,
)
from app.services.quiz import QuizService

router = APIRouter(prefix="/quiz", tags=["quiz"])


@router.get("/active", response_model=SessionRead | None)
async def read_active_session(
    student: StudentDep,
    session: DbSession,
    language: LanguageDep,
    response: Response,
) -> SessionRead | None:
    """Restore the session left open, so a page reload loses nothing.

    Answers a 204 when there is nothing to resume.
    """
    active = await QuizService(session).get_active(student.id, language)
    if active is None:
        response.status_code = status.HTTP_204_NO_CONTENT
    return active


@router.post(
    "/sessions", response_model=SessionRead, status_code=status.HTTP_201_CREATED
)
async def start_session(
    payload: QuizStartRequest, student: StudentDep, session: DbSession
) -> SessionRead:
    """Start a topic run, a self-chosen set, an exam or a mistakes pass."""
    return await QuizService(session).start(student.id, payload)


@router.get("/sessions/{session_id}", response_model=SessionRead)
async def read_session(
    session_id: int,
    student: StudentDep,
    session: DbSession,
    language: LanguageDep,
) -> SessionRead:
    """Re-read a session, including every answer already given."""
    return await QuizService(session).get_session(student.id, session_id, language)


@router.post("/sessions/{session_id}/answers", response_model=AnswerResult)
async def submit_answer(
    session_id: int,
    payload: AnswerRequest,
    student: StudentDep,
    session: DbSession,
    language: LanguageDep,
) -> AnswerResult:
    """Record an answer and return the verdict and explanation."""
    return await QuizService(session).answer(
        student.id, session_id, payload.question_id, payload.answer_id, language
    )


@router.post("/sessions/{session_id}/finish", response_model=SessionResult)
async def finish_session(
    session_id: int,
    student: StudentDep,
    session: DbSession,
    language: LanguageDep,
) -> SessionResult:
    """Finish the session — allowed early, from ten answers on."""
    return await QuizService(session).finish(student.id, session_id, language)


@router.get("/sessions/{session_id}/result", response_model=SessionResult)
async def read_result(
    session_id: int,
    student: StudentDep,
    session: DbSession,
    language: LanguageDep,
) -> SessionResult:
    """The score card of a finished session."""
    return await QuizService(session).get_result(student.id, session_id, language)


@router.get("/history", response_model=Page[ResultBrief])
async def list_history(
    student: StudentDep,
    session: DbSession,
    page: Annotated[int, Query(ge=1)] = 1,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> Page[ResultBrief]:
    """Past attempts and the score of each."""
    return await QuizService(session).list_history(
        student.id, page=page, limit=limit
    )
