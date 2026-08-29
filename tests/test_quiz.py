"""Taking a test: resuming after a reload, marking answers, finishing early."""
from __future__ import annotations

from datetime import timedelta

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.quiz import MIN_ANSWERS_TO_FINISH
from tests.conftest import (
    QUESTIONS_PER_TOPIC,
    create_content,
    create_student,
    sign_in,
)

STUDENT_IIN = "060422501511"


async def start_exam(client: AsyncClient, headers: dict[str, str]) -> dict:
    """Begin an exam run and return the session payload."""
    response = await client.post(
        "/api/v1/quiz/sessions", headers=headers, json={"mode": "exam"}
    )
    assert response.status_code == 201, response.text
    return response.json()


async def answer_at(
    client: AsyncClient, headers: dict[str, str], session: dict, position: int, *, correct: bool
) -> dict:
    """Answer one slot, picking the right or a wrong option on purpose."""
    question = session["questions"][position]
    # Content fixtures mark the first option correct and the rest wrong.
    answer = question["answers"][0 if correct else 1]
    response = await client.post(
        f"/api/v1/quiz/sessions/{session['id']}/answers",
        headers=headers,
        json={"question_id": question["id"], "answer_id": answer["id"]},
    )
    assert response.status_code == 200, response.text
    return response.json()


async def test_exam_session_is_created_with_forty_questions(
    client: AsyncClient, db: AsyncSession
) -> None:
    # Arrange
    await create_content(db)
    await create_student(db, STUDENT_IIN)
    headers = await sign_in(client, STUDENT_IIN)

    # Act
    session = await start_exam(client, headers)

    # Assert
    assert session["total_questions"] == 40
    assert session["answered_count"] == 0
    assert session["current_position"] == 0
    assert session["can_finish"] is False


async def test_correct_answers_are_hidden_until_the_question_is_answered(
    client: AsyncClient, db: AsyncSession
) -> None:
    # Arrange
    await create_content(db)
    await create_student(db, STUDENT_IIN)
    headers = await sign_in(client, STUDENT_IIN)
    session = await start_exam(client, headers)

    # Assert — nothing in the payload reveals the right option yet
    assert all(
        answer["is_correct"] is None
        for question in session["questions"]
        for answer in question["answers"]
    )
    assert all(question["explanation"] is None for question in session["questions"])


async def test_answering_reveals_the_verdict_and_explanation(
    client: AsyncClient, db: AsyncSession
) -> None:
    # Arrange
    await create_content(db)
    await create_student(db, STUDENT_IIN)
    headers = await sign_in(client, STUDENT_IIN)
    session = await start_exam(client, headers)

    # Act
    wrong = await answer_at(client, headers, session, 0, correct=False)

    # Assert — one answer is already enough to hand the test in
    assert wrong["is_correct"] is False
    assert wrong["explanation"].startswith("Пояснение")
    assert wrong["answered_count"] == 1
    assert wrong["can_finish"] is True


async def test_the_navigation_strip_marks_right_and_wrong_answers(
    client: AsyncClient, db: AsyncSession
) -> None:
    # Arrange
    await create_content(db)
    await create_student(db, STUDENT_IIN)
    headers = await sign_in(client, STUDENT_IIN)
    session = await start_exam(client, headers)

    # Act
    await answer_at(client, headers, session, 0, correct=True)
    await answer_at(client, headers, session, 1, correct=False)
    reread = (
        await client.get(f"/api/v1/quiz/sessions/{session['id']}", headers=headers)
    ).json()

    # Assert — this is what colours the numbered chips at the top
    items = reread["items"]
    assert items[0]["is_answered"] is True and items[0]["is_correct"] is True
    assert items[1]["is_answered"] is True and items[1]["is_correct"] is False
    assert items[2]["is_answered"] is False and items[2]["is_correct"] is None


async def test_a_reload_restores_every_answer_and_the_current_position(
    client: AsyncClient, db: AsyncSession
) -> None:
    # Arrange
    await create_content(db)
    await create_student(db, STUDENT_IIN)
    headers = await sign_in(client, STUDENT_IIN)
    session = await start_exam(client, headers)
    for position in range(3):
        await answer_at(client, headers, session, position, correct=position != 1)

    # Act — what the client does on a fresh page load
    restored = await client.get("/api/v1/quiz/active", headers=headers)

    # Assert
    assert restored.status_code == 200
    payload = restored.json()
    assert payload["id"] == session["id"]
    assert payload["answered_count"] == 3
    assert payload["correct_count"] == 2
    assert payload["current_position"] == 3
    assert [item["is_correct"] for item in payload["items"][:3]] == [True, False, True]
    # Already-answered questions come back with their explanation revealed
    assert payload["questions"][0]["explanation"] is not None
    assert payload["questions"][3]["explanation"] is None


async def test_there_is_nothing_to_restore_before_a_session_starts(
    client: AsyncClient, db: AsyncSession
) -> None:
    # Arrange
    await create_content(db)
    await create_student(db, STUDENT_IIN)
    headers = await sign_in(client, STUDENT_IIN)

    # Act
    response = await client.get("/api/v1/quiz/active", headers=headers)

    # Assert
    assert response.status_code == 204


async def test_a_question_cannot_be_answered_twice(
    client: AsyncClient, db: AsyncSession
) -> None:
    # Arrange
    await create_content(db)
    await create_student(db, STUDENT_IIN)
    headers = await sign_in(client, STUDENT_IIN)
    session = await start_exam(client, headers)
    await answer_at(client, headers, session, 0, correct=True)

    # Act — a stale tab replaying the same answer
    question = session["questions"][0]
    response = await client.post(
        f"/api/v1/quiz/sessions/{session['id']}/answers",
        headers=headers,
        json={
            "question_id": question["id"],
            "answer_id": question["answers"][1]["id"],
        },
    )

    # Assert
    assert response.status_code == 409
    assert response.json()["error"] == "На этот вопрос уже дан ответ"


async def test_finishing_is_refused_before_any_answer(
    client: AsyncClient, db: AsyncSession
) -> None:
    # Arrange
    await create_content(db)
    await create_student(db, STUDENT_IIN)
    headers = await sign_in(client, STUDENT_IIN)
    session = await start_exam(client, headers)

    # Act — nothing has been answered yet
    response = await client.post(
        f"/api/v1/quiz/sessions/{session['id']}/finish", headers=headers
    )

    # Assert
    assert response.status_code == 409


async def test_student_may_finish_after_a_single_answer(
    client: AsyncClient, db: AsyncSession
) -> None:
    # Arrange
    await create_content(db)
    await create_student(db, STUDENT_IIN)
    headers = await sign_in(client, STUDENT_IIN)
    session = await start_exam(client, headers)

    # Act
    feedback = await answer_at(client, headers, session, 0, correct=True)
    finished = await client.post(
        f"/api/v1/quiz/sessions/{session['id']}/finish", headers=headers
    )

    # Assert
    assert MIN_ANSWERS_TO_FINISH == 1
    assert feedback["can_finish"] is True
    assert finished.status_code == 200, finished.text
    result = finished.json()
    assert result["answered_count"] == 1
    assert result["correct_count"] == 1
    assert result["total_questions"] == 40
    # Unanswered questions still count against the score
    assert result["score_percent"] == 2
    assert result["is_passed"] is False
    assert len(result["mistakes"]) == 39


async def test_a_finished_session_is_no_longer_resumable(
    client: AsyncClient, db: AsyncSession
) -> None:
    # Arrange
    await create_content(db)
    await create_student(db, STUDENT_IIN)
    headers = await sign_in(client, STUDENT_IIN)
    session = await start_exam(client, headers)
    await answer_at(client, headers, session, 0, correct=True)
    await client.post(f"/api/v1/quiz/sessions/{session['id']}/finish", headers=headers)

    # Act
    response = await client.get("/api/v1/quiz/active", headers=headers)

    # Assert
    assert response.status_code == 204


async def test_wrong_answers_feed_the_mistakes_mode(
    client: AsyncClient, db: AsyncSession
) -> None:
    # Arrange
    await create_content(db)
    await create_student(db, STUDENT_IIN)
    headers = await sign_in(client, STUDENT_IIN)
    session = await start_exam(client, headers)
    for position in range(3):
        await answer_at(client, headers, session, position, correct=False)

    # Act
    mistakes = await client.post(
        "/api/v1/quiz/sessions", headers=headers, json={"mode": "mistakes"}
    )

    # Assert
    assert mistakes.status_code == 201, mistakes.text
    assert mistakes.json()["total_questions"] == 3


async def test_a_correct_answer_removes_the_question_from_the_mistakes(
    client: AsyncClient, db: AsyncSession
) -> None:
    # Arrange
    await create_content(db)
    await create_student(db, STUDENT_IIN)
    headers = await sign_in(client, STUDENT_IIN)
    first = await start_exam(client, headers)
    for position in range(3):
        await answer_at(client, headers, first, position, correct=False)

    # Act — retry the mistakes and get them all right this time
    retry = (
        await client.post(
            "/api/v1/quiz/sessions", headers=headers, json={"mode": "mistakes"}
        )
    ).json()
    for position in range(3):
        await answer_at(client, headers, retry, position, correct=True)
    empty = await client.post(
        "/api/v1/quiz/sessions", headers=headers, json={"mode": "mistakes"}
    )

    # Assert — the collection is empty, so there is nothing left to practise
    assert empty.status_code == 409
    assert empty.json()["error"] == "Для этого режима нет доступных вопросов"


async def test_topic_session_uses_every_question_of_the_topic(
    client: AsyncClient, db: AsyncSession
) -> None:
    # Arrange
    topic = await create_content(db)
    await create_student(db, STUDENT_IIN)
    headers = await sign_in(client, STUDENT_IIN)

    # Act
    response = await client.post(
        "/api/v1/quiz/sessions",
        headers=headers,
        json={"mode": "topic", "topic_id": topic.id, "language": "kz"},
    )

    # Assert
    session = response.json()
    assert session["total_questions"] == QUESTIONS_PER_TOPIC
    assert session["title"] == "1. Жалпы ережелер"
    assert session["questions"][0]["text"].startswith("Сұрақ")


async def test_finished_sessions_appear_in_the_history(
    client: AsyncClient, db: AsyncSession
) -> None:
    # Arrange
    await create_content(db)
    await create_student(db, STUDENT_IIN)
    headers = await sign_in(client, STUDENT_IIN)
    session = await start_exam(client, headers)
    for position in range(3):
        await answer_at(client, headers, session, position, correct=True)
    await client.post(f"/api/v1/quiz/sessions/{session['id']}/finish", headers=headers)

    # Act
    history = await client.get("/api/v1/quiz/history", headers=headers)

    # Assert
    assert history.status_code == 200
    payload = history.json()
    assert payload["total"] == 1
    assert payload["items"][0]["correct_count"] == 3
    assert payload["items"][0]["mode"]["value"] == "exam"


async def test_one_student_cannot_open_another_students_session(
    client: AsyncClient, db: AsyncSession
) -> None:
    # Arrange
    await create_content(db)
    await create_student(db, STUDENT_IIN)
    await create_student(db, "770000000007")
    owner_headers = await sign_in(client, STUDENT_IIN)
    session = await start_exam(client, owner_headers)
    intruder_headers = await sign_in(client, "770000000007")

    # Act
    response = await client.get(
        f"/api/v1/quiz/sessions/{session['id']}", headers=intruder_headers
    )

    # Assert
    assert response.status_code == 404


async def test_shared_media_resolves_to_one_url_for_every_question(
    client: AsyncClient, db: AsyncSession
) -> None:
    # Arrange — the fixture points all questions at a single deduplicated asset
    await create_content(db)
    await create_student(db, STUDENT_IIN)
    headers = await sign_in(client, STUDENT_IIN)

    # Act
    session = await start_exam(client, headers)

    # Assert
    urls = {q["situation_video"]["url"] for q in session["questions"]}
    assert urls == {"/media/videos/situations/shared.mp4"}


async def test_the_topic_catalogue_loads_after_a_finished_topic_run(
    client: AsyncClient, db: AsyncSession
) -> None:
    """The catalogue computes a best score per topic.

    Doing that in one query would nest an aggregate inside another, which
    PostgreSQL refuses outright — so the catalogue is exercised here with a
    finished run behind it, where a naive query would break.
    """
    # Arrange
    topic = await create_content(db)
    await create_student(db, STUDENT_IIN)
    headers = await sign_in(client, STUDENT_IIN)
    started = (
        await client.post(
            "/api/v1/quiz/sessions",
            headers=headers,
            json={"mode": "topic", "topic_id": topic.id},
        )
    ).json()
    for position in range(4):
        await answer_at(client, headers, started, position, correct=position < 3)
    await client.post(f"/api/v1/quiz/sessions/{started['id']}/finish", headers=headers)

    # Act
    response = await client.get("/api/v1/topics", headers=headers)

    # Assert
    assert response.status_code == 200, response.text
    tile = response.json()[0]
    assert tile["question_count"] == QUESTIONS_PER_TOPIC
    # 3 correct out of the topic's full question set
    assert tile["best_percent"] == round(3 / QUESTIONS_PER_TOPIC * 100)


async def test_the_catalogue_shows_no_best_score_before_any_attempt(
    client: AsyncClient, db: AsyncSession
) -> None:
    # Arrange
    await create_content(db)
    await create_student(db, STUDENT_IIN)
    headers = await sign_in(client, STUDENT_IIN)

    # Act
    response = await client.get("/api/v1/topics", headers=headers)

    # Assert
    assert response.status_code == 200
    assert response.json()[0]["best_percent"] is None


async def test_the_exam_is_timed_and_training_is_not(
    client: AsyncClient, db: AsyncSession
) -> None:
    # Arrange
    await create_content(db)
    await create_student(db, STUDENT_IIN)
    headers = await sign_in(client, STUDENT_IIN)

    # Act
    exam = await start_exam(client, headers)
    training = (
        await client.post(
            "/api/v1/quiz/sessions", headers=headers, json={"mode": "training"}
        )
    ).json()

    # Assert — 40 minutes for the exam, no clock for training
    assert exam["time_limit_seconds"] == 40 * 60
    assert 0 < exam["seconds_left"] <= 40 * 60
    assert training["time_limit_seconds"] is None
    assert training["seconds_left"] is None
    assert training["total_questions"] == 40


async def test_a_run_whose_clock_ran_out_is_closed_not_resumed(
    client: AsyncClient, db: AsyncSession
) -> None:
    # Arrange
    await create_content(db)
    await create_student(db, STUDENT_IIN)
    headers = await sign_in(client, STUDENT_IIN)
    session = await start_exam(client, headers)
    await answer_at(client, headers, session, 0, correct=True)

    # Act — wind the start time back past the 40-minute limit
    from sqlalchemy import select

    from app.models.quiz import QuizSession

    row = await db.scalar(select(QuizSession).where(QuizSession.id == session["id"]))
    assert row is not None
    row.started_at = row.started_at - timedelta(minutes=41)
    await db.commit()

    # A late answer is refused, and the run closes itself on the way out.
    answered = await client.post(
        f"/api/v1/quiz/sessions/{session['id']}/answers",
        headers=headers,
        json={
            "question_id": session["questions"][1]["id"],
            "answer_id": session["questions"][1]["answers"][0]["id"],
        },
    )
    resumed = await client.get("/api/v1/quiz/active", headers=headers)

    # Assert
    assert answered.status_code == 409
    assert "Время вышло" in answered.json()["error"]
    assert resumed.status_code == 204


async def test_the_result_reviews_every_question_not_only_the_failed_ones(
    client: AsyncClient, db: AsyncSession
) -> None:
    # Arrange
    await create_content(db)
    await create_student(db, STUDENT_IIN)
    headers = await sign_in(client, STUDENT_IIN)
    session = await start_exam(client, headers)
    for position in range(5):
        await answer_at(client, headers, session, position, correct=position % 2 == 0)

    # Act
    result = (
        await client.post(
            f"/api/v1/quiz/sessions/{session['id']}/finish", headers=headers
        )
    ).json()

    # Assert — the review covers the whole run, right answers included
    assert len(result["review"]) == 40
    answered = [entry for entry in result["review"] if entry["is_answered"]]
    assert len(answered) == 5
    assert [entry["is_correct"] for entry in answered] == [
        True,
        False,
        True,
        False,
        True,
    ]
    assert all(entry["correct_answer_text"] for entry in result["review"])
    # Mistakes remain the failed subset of the same list
    assert result["mistakes"] == [e for e in result["review"] if not e["is_correct"]]


async def test_media_urls_escape_percent_signs_in_file_names(
    client: AsyncClient, db: AsyncSession
) -> None:
    """The export wrote files under already-encoded names.

    A file literally called `%D0%B1....mp4` must reach the server as
    `%25D0%25B1...`, otherwise the browser decodes the escape and requests a
    name that does not exist on disk.
    """
    # Arrange
    from sqlalchemy import select

    from app.models.media_asset import MediaAsset

    await create_content(db)
    asset = await db.scalar(select(MediaAsset))
    assert asset is not None
    asset.rel_path = "media/videos/explanations/ru/IMG_%D0%B2%D0%BE.MOV"
    await db.commit()

    await create_student(db, STUDENT_IIN)
    headers = await sign_in(client, STUDENT_IIN)

    # Act
    session = await start_exam(client, headers)

    # Assert
    url = session["questions"][0]["situation_video"]["url"]
    assert url == "/media/media/videos/explanations/ru/IMG_%25D0%25B2%25D0%25BE.MOV"
