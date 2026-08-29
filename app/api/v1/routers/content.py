"""Catalogue reads: topics, their questions and the lesson videos."""
from __future__ import annotations

from fastapi import APIRouter

from app.api.deps import CurrentUserDep, DbSession, LanguageDep
from app.schemas.content import TopicBrief, TopicDetail, VideoRead
from app.services.content import ContentService

router = APIRouter(tags=["content"])


@router.get("/topics", response_model=list[TopicBrief])
async def list_topics(
    user: CurrentUserDep, session: DbSession, language: LanguageDep
) -> list[TopicBrief]:
    """Topic tiles with the caller's best score for each."""
    return await ContentService(session).list_topics(user.id, language)


@router.get("/topics/{topic_id}", response_model=TopicDetail)
async def read_topic(
    topic_id: int, user: CurrentUserDep, session: DbSession, language: LanguageDep
) -> TopicDetail:
    """One topic with its questions; correct answers are withheld."""
    return await ContentService(session).get_topic(topic_id, user.id, language)


@router.get("/videos", response_model=list[VideoRead])
async def list_videos(
    _: CurrentUserDep, session: DbSession, language: LanguageDep
) -> list[VideoRead]:
    """Lesson videos in display order."""
    return await ContentService(session).list_videos(language)
