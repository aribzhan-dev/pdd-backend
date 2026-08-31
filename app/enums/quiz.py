"""Quiz vocabulary: how a session was started and how it ended."""
from __future__ import annotations

import enum


class QuizMode(str, enum.Enum):
    """What kind of run the student started."""

    TOPIC = "topic"
    EXAM = "exam"
    TRAINING = "training"
    MISTAKES = "mistakes"

    @property
    def label(self) -> str:
        """Human-readable name shown in the UI (Russian)."""
        return QUIZ_MODE_LABELS[self]

    @property
    def reveals_answers_immediately(self) -> bool:
        """Whether the verdict is shown as soon as a question is answered.

        The exam mirrors the real one: it records the answer and moves on,
        saying nothing about right or wrong until the whole run is handed in.
        Every other mode is for learning, so feedback comes at once.
        """
        return self is not QuizMode.EXAM


class QuizStatus(str, enum.Enum):
    """Where a session stands. IN_PROGRESS sessions are resumable."""

    IN_PROGRESS = "in_progress"
    FINISHED = "finished"

    @property
    def label(self) -> str:
        """Human-readable name shown in the UI (Russian)."""
        return QUIZ_STATUS_LABELS[self]


QUIZ_MODE_LABELS: dict[QuizMode, str] = {
    QuizMode.TOPIC: "Тема",
    QuizMode.EXAM: "40 вопросов (аналогично СпецЦОН)",
    QuizMode.TRAINING: "В режиме обучения",
    QuizMode.MISTAKES: "Работа над ошибками",
}

QUIZ_STATUS_LABELS: dict[QuizStatus, str] = {
    QuizStatus.IN_PROGRESS: "В процессе",
    QuizStatus.FINISHED: "Завершён",
}
