"""Taking a test: resuming after a reload, marking answers, finishing early."""
from __future__ import annotations

from datetime import timedelta

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.quiz import MIN_ANSWERS_TO_FINISH
from app.services.content import TOPIC_PART_SIZE
from app.services.quiz import CUSTOM_QUESTION_LIMIT
from tests.conftest import (
    QUESTIONS_PER_TOPIC,
    add_same_wording_questions,
    create_content,
    create_extra_topic,
    create_student,
    sign_in,
)

STUDENT_IIN = "060422501511"

#: The content fixtures give every question three options and mark this one
#: correct. Answers are served in a shuffled order, so tests match on the text.
CORRECT_ANSWER_TEXT = "Ответ 0"


async def start_exam(client: AsyncClient, headers: dict[str, str]) -> dict:
    """Begin an exam run and return the session payload."""
    response = await client.post(
        "/api/v1/quiz/sessions", headers=headers, json={"mode": "exam"}
    )
    assert response.status_code == 201, response.text
    return response.json()


async def start_training(client: AsyncClient, headers: dict[str, str]) -> dict:
    """Begin a training run — the mode that gives feedback as you go."""
    response = await client.post(
        "/api/v1/quiz/sessions", headers=headers, json={"mode": "training"}
    )
    assert response.status_code == 201, response.text
    return response.json()


async def answer_at(
    client: AsyncClient, headers: dict[str, str], session: dict, position: int, *, correct: bool
) -> dict:
    """Answer one slot, picking the right or a wrong option on purpose."""
    question = session["questions"][position]
    # Content fixtures mark the option reading CORRECT_ANSWER_TEXT as the right
    # one. Options come back shuffled, so it has to be found by text — its
    # position differs from question to question.
    answer = next(
        option
        for option in question["answers"]
        if (option["text"] == CORRECT_ANSWER_TEXT) is correct
    )
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
    session = await start_training(client, headers)

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
    session = await start_training(client, headers)

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
    session = await start_training(client, headers)
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


async def test_the_exam_says_nothing_about_right_or_wrong_while_it_runs(
    client: AsyncClient, db: AsyncSession
) -> None:
    """The exam mirrors the real one: answer, move on, find out at the end."""
    # Arrange
    await create_content(db)
    await create_student(db, STUDENT_IIN)
    headers = await sign_in(client, STUDENT_IIN)
    session = await start_exam(client, headers)

    # Act
    feedback = await answer_at(client, headers, session, 0, correct=False)

    # Assert — the answer is recorded, but nothing is given away
    assert feedback["reveals_answer"] is False
    assert feedback["is_correct"] is None
    assert feedback["correct_answer_id"] is None
    assert feedback["explanation"] is None
    assert feedback["explanation_video_url"] is None
    assert feedback["answered_count"] == 1


async def test_the_exam_strip_shows_answered_but_not_correctness(
    client: AsyncClient, db: AsyncSession
) -> None:
    # Arrange
    await create_content(db)
    await create_student(db, STUDENT_IIN)
    headers = await sign_in(client, STUDENT_IIN)
    session = await start_exam(client, headers)
    await answer_at(client, headers, session, 0, correct=True)
    await answer_at(client, headers, session, 1, correct=False)

    # Act
    reread = (
        await client.get(f"/api/v1/quiz/sessions/{session['id']}", headers=headers)
    ).json()

    # Assert — the chips may only say "answered", never green or red
    assert reread["reveals_answers"] is False
    assert reread["items"][0]["is_answered"] is True
    assert reread["items"][0]["is_correct"] is None
    assert reread["items"][1]["is_correct"] is None
    assert all(q["explanation"] is None for q in reread["questions"])
    assert all(
        a["is_correct"] is None for q in reread["questions"] for a in q["answers"]
    )


async def test_finishing_the_exam_reveals_everything(
    client: AsyncClient, db: AsyncSession
) -> None:
    # Arrange
    await create_content(db)
    await create_student(db, STUDENT_IIN)
    headers = await sign_in(client, STUDENT_IIN)
    session = await start_exam(client, headers)
    for position in range(3):
        await answer_at(client, headers, session, position, correct=position != 1)

    # Act
    result = (
        await client.post(
            f"/api/v1/quiz/sessions/{session['id']}/finish", headers=headers
        )
    ).json()
    reread = (
        await client.get(f"/api/v1/quiz/sessions/{session['id']}", headers=headers)
    ).json()

    # Assert — the score card is complete and the review is now readable
    assert result["correct_count"] == 2
    assert len([e for e in result["review"] if e["is_answered"]]) == 3
    assert reread["reveals_answers"] is True
    assert reread["items"][0]["is_correct"] is True
    assert reread["items"][1]["is_correct"] is False


async def test_training_mode_gives_feedback_straight_away(
    client: AsyncClient, db: AsyncSession
) -> None:
    # Arrange
    await create_content(db)
    await create_student(db, STUDENT_IIN)
    headers = await sign_in(client, STUDENT_IIN)
    session = await start_training(client, headers)

    # Act
    feedback = await answer_at(client, headers, session, 0, correct=True)

    # Assert
    assert feedback["reveals_answer"] is True
    assert feedback["is_correct"] is True
    assert feedback["correct_answer_id"] is not None
    assert feedback["explanation"] is not None


async def test_switching_language_re_renders_the_same_session(
    client: AsyncClient, db: AsyncSession
) -> None:
    """The switcher must change the questions, not be ignored.

    A session remembers the language it started in, but that is a default —
    asking for the other language returns the same questions translated,
    rather than the language the run happened to begin with.
    """
    # Arrange — started in Russian
    topic = await create_content(db)
    await create_student(db, STUDENT_IIN)
    headers = await sign_in(client, STUDENT_IIN)
    started = (
        await client.post(
            "/api/v1/quiz/sessions",
            headers=headers,
            json={"mode": "topic", "topic_id": topic.id, "language": "ru"},
        )
    ).json()
    assert started["questions"][0]["text"].startswith("Вопрос")

    # Act — the same session, asked for in Kazakh
    kazakh = (
        await client.get(
            f"/api/v1/quiz/sessions/{started['id']}?lang=kz", headers=headers
        )
    ).json()

    # Assert
    assert kazakh["id"] == started["id"]
    assert kazakh["language"] == "kz"
    assert kazakh["questions"][0]["text"].startswith("Сұрақ")
    assert kazakh["title"] == "1. Жалпы ережелер"


async def test_the_resumed_session_also_follows_the_language(
    client: AsyncClient, db: AsyncSession
) -> None:
    # Arrange
    topic = await create_content(db)
    await create_student(db, STUDENT_IIN)
    headers = await sign_in(client, STUDENT_IIN)
    await client.post(
        "/api/v1/quiz/sessions",
        headers=headers,
        json={"mode": "topic", "topic_id": topic.id, "language": "ru"},
    )

    # Act — what the page does on load after the switcher moved
    restored = (await client.get("/api/v1/quiz/active?lang=kz", headers=headers)).json()

    # Assert
    assert restored["questions"][0]["text"].startswith("Сұрақ")


async def test_the_result_screen_follows_the_language_too(
    client: AsyncClient, db: AsyncSession
) -> None:
    # Arrange
    topic = await create_content(db)
    await create_student(db, STUDENT_IIN)
    headers = await sign_in(client, STUDENT_IIN)
    started = (
        await client.post(
            "/api/v1/quiz/sessions",
            headers=headers,
            json={"mode": "topic", "topic_id": topic.id, "language": "ru"},
        )
    ).json()
    await answer_at(client, headers, started, 0, correct=False)

    # Act
    result = (
        await client.post(
            f"/api/v1/quiz/sessions/{started['id']}/finish?lang=kz", headers=headers
        )
    ).json()

    # Assert — the mistake review is translated as well
    assert result["mistakes"][0]["question_text"].startswith("Сұрақ")


# --- Custom runs: a set drawn from several topics the student picked ---------


async def start_custom(
    client: AsyncClient, headers: dict[str, str], topic_ids: list[int]
) -> dict:
    """Begin a run over a self-chosen set of topics."""
    response = await client.post(
        "/api/v1/quiz/sessions",
        headers=headers,
        json={"mode": "custom", "topic_ids": topic_ids},
    )
    assert response.status_code == 201, response.text
    return response.json()


async def test_custom_session_caps_the_draw_at_forty_questions(
    client: AsyncClient, db: AsyncSession
) -> None:
    """A selection wider than the cap is sampled down, not truncated whole."""
    # Arrange — 45 + 10 questions available, well over the cap
    big = await create_content(db)
    small = await create_extra_topic(db, number=2, question_count=10)
    await create_student(db, STUDENT_IIN)
    headers = await sign_in(client, STUDENT_IIN)

    # Act
    session = await start_custom(client, headers, [big.id, small.id])

    # Assert
    assert session["total_questions"] == CUSTOM_QUESTION_LIMIT
    assert len(session["questions"]) == CUSTOM_QUESTION_LIMIT


async def test_custom_session_takes_every_question_when_below_the_cap(
    client: AsyncClient, db: AsyncSession
) -> None:
    """Under the cap the run holds the whole selection, not a padded forty."""
    # Arrange
    first = await create_extra_topic(db, number=2, question_count=10)
    second = await create_extra_topic(db, number=3, question_count=7)
    await create_student(db, STUDENT_IIN)
    headers = await sign_in(client, STUDENT_IIN)

    # Act
    session = await start_custom(client, headers, [first.id, second.id])

    # Assert
    assert session["total_questions"] == 17


async def test_custom_session_draws_only_from_the_chosen_topics(
    client: AsyncClient, db: AsyncSession
) -> None:
    # Arrange — an unchosen topic sits in the catalogue alongside the chosen one
    await create_content(db)
    chosen = await create_extra_topic(db, number=2, question_count=10)
    await create_student(db, STUDENT_IIN)
    headers = await sign_in(client, STUDENT_IIN)

    # Act
    session = await start_custom(client, headers, [chosen.id])

    # Assert
    assert session["total_questions"] == 10
    assert all(
        question["text"].startswith("Тема 2,")
        for question in session["questions"]
    )


async def test_custom_session_repeats_in_the_selection_are_ignored(
    client: AsyncClient, db: AsyncSession
) -> None:
    """A stale client sending the same id twice must not double that topic."""
    # Arrange
    topic = await create_extra_topic(db, number=2, question_count=10)
    await create_student(db, STUDENT_IIN)
    headers = await sign_in(client, STUDENT_IIN)

    # Act
    session = await start_custom(client, headers, [topic.id, topic.id])

    # Assert
    assert session["total_questions"] == 10


async def test_custom_session_needs_at_least_one_topic(
    client: AsyncClient, db: AsyncSession
) -> None:
    # Arrange
    await create_content(db)
    await create_student(db, STUDENT_IIN)
    headers = await sign_in(client, STUDENT_IIN)

    # Act
    response = await client.post(
        "/api/v1/quiz/sessions",
        headers=headers,
        json={"mode": "custom", "topic_ids": []},
    )

    # Assert
    assert response.status_code == 409
    assert response.json()["error"] == "Выберите хотя бы одну тему"


async def test_custom_session_is_untimed_and_gives_feedback_at_once(
    client: AsyncClient, db: AsyncSession
) -> None:
    """A custom run is for learning, so it has no clock and marks as it goes."""
    # Arrange
    topic = await create_extra_topic(db, number=2, question_count=10)
    await create_student(db, STUDENT_IIN)
    headers = await sign_in(client, STUDENT_IIN)

    # Act
    session = await start_custom(client, headers, [topic.id])
    verdict = await answer_at(client, headers, session, 0, correct=True)

    # Assert
    assert session["time_limit_seconds"] is None
    assert session["seconds_left"] is None
    assert session["reveals_answers"] is True
    assert verdict["is_correct"] is True
    assert verdict["reveals_answer"] is True


# --- Shuffling: options within a question, questions within a topic ----------


def _correct_option_positions(session: dict) -> list[int]:
    """Where the correct option landed in each question of the session."""
    return [
        [option["text"] for option in question["answers"]].index(
            CORRECT_ANSWER_TEXT
        )
        for question in session["questions"]
    ]


async def test_answer_options_are_shuffled_within_a_session(
    client: AsyncClient, db: AsyncSession
) -> None:
    """The correct option must not sit in the same slot every time.

    With three options over forty questions, a run that never moves it is
    beyond coincidence — so seeing more than one position proves the shuffle.
    """
    # Arrange
    await create_content(db)
    await create_student(db, STUDENT_IIN)
    headers = await sign_in(client, STUDENT_IIN)

    # Act
    session = await start_exam(client, headers)

    # Assert
    assert len(set(_correct_option_positions(session))) > 1


async def test_answer_order_survives_a_reload(
    client: AsyncClient, db: AsyncSession
) -> None:
    """The shuffle is drawn once per slot, not per request.

    Re-reading a session must not move the options under the student — they
    would otherwise jump every time the page reloads or the strip is used.
    """
    # Arrange
    await create_content(db)
    await create_student(db, STUDENT_IIN)
    headers = await sign_in(client, STUDENT_IIN)
    session = await start_exam(client, headers)

    # Act
    resumed = await client.get("/api/v1/quiz/active", headers=headers)

    # Assert
    assert resumed.status_code == 200
    assert _correct_option_positions(resumed.json()) == _correct_option_positions(
        session
    )


async def test_topic_runs_draw_their_questions_in_a_fresh_order(
    client: AsyncClient, db: AsyncSession
) -> None:
    """Two attempts at the same topic must not walk it in the same sequence."""
    # Arrange
    topic = await create_content(db)
    await create_student(db, STUDENT_IIN)
    headers = await sign_in(client, STUDENT_IIN)

    async def start_topic_run() -> list[int]:
        response = await client.post(
            "/api/v1/quiz/sessions",
            headers=headers,
            json={"mode": "topic", "topic_id": topic.id},
        )
        assert response.status_code == 201, response.text
        return [question["id"] for question in response.json()["questions"]]

    # Act — the second run abandons the first, which is the normal flow
    first = await start_topic_run()
    second = await start_topic_run()

    # Assert — the same questions, a different sequence
    assert sorted(first) == sorted(second)
    assert len(first) == QUESTIONS_PER_TOPIC
    assert first != second


async def test_a_drawn_run_never_asks_the_same_wording_twice(
    client: AsyncClient, db: AsyncSession
) -> None:
    """Two questions that read alike must not land in one run.

    They are different questions — different pictures, different options — but
    a student reading the same sentence twice in one test concludes the test
    is broken.
    """
    # Arrange — six questions sharing one wording, among the topic's own 45
    topic = await create_content(db)
    await add_same_wording_questions(
        db, topic, text="Кому Вы уступите дорогу?", count=6
    )
    await create_student(db, STUDENT_IIN)
    headers = await sign_in(client, STUDENT_IIN)

    # Act
    session = await start_exam(client, headers)

    # Assert
    texts = [question["text"] for question in session["questions"]]
    assert len(texts) == len(set(texts))


async def test_a_drawn_run_still_fills_up_to_forty(
    client: AsyncClient, db: AsyncSession
) -> None:
    """Dropping repeated wordings must not quietly shorten the exam."""
    # Arrange
    topic = await create_content(db)
    await add_same_wording_questions(
        db, topic, text="Кому Вы уступите дорогу?", count=6
    )
    await create_student(db, STUDENT_IIN)
    headers = await sign_in(client, STUDENT_IIN)

    # Act
    session = await start_exam(client, headers)

    # Assert
    assert session["total_questions"] == CUSTOM_QUESTION_LIMIT


# --- Parts: a long chapter split into sittings ------------------------------


async def start_topic_part(
    client: AsyncClient, headers: dict[str, str], topic_id: int, part: int | None
) -> dict:
    """Run a topic, optionally narrowed to one of its parts."""
    body = {"mode": "topic", "topic_id": topic_id}
    if part is not None:
        body["part"] = part
    response = await client.post(
        "/api/v1/quiz/sessions", headers=headers, json=body
    )
    assert response.status_code == 201, response.text
    return response.json()


async def test_the_catalogue_reports_how_many_parts_a_topic_has(
    client: AsyncClient, db: AsyncSession
) -> None:
    """A topic is split only once it outgrows a single sitting."""
    # Arrange — 45 questions is one part too many; 10 is comfortably one
    await create_content(db)
    await create_extra_topic(db, number=2, question_count=10)
    await create_student(db, STUDENT_IIN)
    headers = await sign_in(client, STUDENT_IIN)

    # Act
    response = await client.get("/api/v1/topics", headers=headers)

    # Assert
    by_number = {topic["number"]: topic for topic in response.json()}
    assert by_number[1]["question_count"] == QUESTIONS_PER_TOPIC
    assert by_number[1]["part_count"] == 2
    assert by_number[2]["part_count"] == 1


async def test_a_part_holds_one_sitting_and_the_last_one_the_remainder(
    client: AsyncClient, db: AsyncSession
) -> None:
    # Arrange — 45 questions: 40 in the first part, 5 in the second
    topic = await create_content(db)
    await create_student(db, STUDENT_IIN)
    headers = await sign_in(client, STUDENT_IIN)

    # Act
    first = await start_topic_part(client, headers, topic.id, 1)
    second = await start_topic_part(client, headers, topic.id, 2)

    # Assert
    assert first["total_questions"] == TOPIC_PART_SIZE
    assert second["total_questions"] == QUESTIONS_PER_TOPIC - TOPIC_PART_SIZE


async def test_the_parts_cover_the_topic_exactly_once(
    client: AsyncClient, db: AsyncSession
) -> None:
    """Working through the parts must cover the chapter, and cover it once.

    An overlap would make a student answer the same question twice; a gap
    would leave part of the chapter unreachable.
    """
    # Arrange
    topic = await create_content(db)
    await create_student(db, STUDENT_IIN)
    headers = await sign_in(client, STUDENT_IIN)

    # Act
    first = await start_topic_part(client, headers, topic.id, 1)
    second = await start_topic_part(client, headers, topic.id, 2)
    whole = await start_topic_part(client, headers, topic.id, None)

    # Assert
    ids_first = {q["id"] for q in first["questions"]}
    ids_second = {q["id"] for q in second["questions"]}
    assert not ids_first & ids_second
    assert ids_first | ids_second == {q["id"] for q in whole["questions"]}


async def test_a_part_holds_the_same_questions_every_time(
    client: AsyncClient, db: AsyncSession
) -> None:
    """The slice is cut from the authored order, not from the shuffle.

    Questions inside a run are shuffled, but which questions belong to part
    two must not move — otherwise a student could never work through a chapter
    part by part and know they had seen all of it.
    """
    # Arrange
    topic = await create_content(db)
    await create_student(db, STUDENT_IIN)
    headers = await sign_in(client, STUDENT_IIN)

    # Act
    first = await start_topic_part(client, headers, topic.id, 2)
    again = await start_topic_part(client, headers, topic.id, 2)

    # Assert
    assert {q["id"] for q in first["questions"]} == {
        q["id"] for q in again["questions"]
    }


async def test_asking_for_a_part_the_topic_does_not_have_is_refused(
    client: AsyncClient, db: AsyncSession
) -> None:
    # Arrange — 45 questions make two parts, so there is no third
    topic = await create_content(db)
    await create_student(db, STUDENT_IIN)
    headers = await sign_in(client, STUDENT_IIN)

    # Act
    response = await client.post(
        "/api/v1/quiz/sessions",
        headers=headers,
        json={"mode": "topic", "topic_id": topic.id, "part": 3},
    )

    # Assert
    assert response.status_code == 409
    assert "2" in response.json()["error"]


async def test_a_topic_asked_for_whole_is_still_served_whole(
    client: AsyncClient, db: AsyncSession
) -> None:
    """Leaving the part out keeps the behaviour clients had before parts."""
    # Arrange
    topic = await create_content(db)
    await create_student(db, STUDENT_IIN)
    headers = await sign_in(client, STUDENT_IIN)

    # Act
    session = await start_topic_part(client, headers, topic.id, None)

    # Assert
    assert session["total_questions"] == QUESTIONS_PER_TOPIC
