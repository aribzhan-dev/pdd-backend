"""Check the question bank against itself and print what looks wrong.

This is a read-only report, meant to be run against the live database before
comparing topic totals with the official source. It answers two questions the
import cannot answer for itself: is every question well-formed, and is it
filed under a plausible topic.

    python3 -m scripts.audit_content

Nothing here decides that a question is misfiled — only the official
curriculum can. What it does is narrow a thousand rows down to the handful
worth reading by hand.
"""
from __future__ import annotations

import asyncio
import re
from collections import Counter, defaultdict

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.db import AsyncSessionLocal
from app.models.question import Question
from app.models.topic import Topic

#: A topic holding fewer than this is either genuinely tiny or a leftover from
#: a half-finished import. Either way it is worth a look.
THIN_TOPIC_THRESHOLD = 3

#: How many example rows to print per finding, so the report stays readable.
EXAMPLES = 8


def normalise(text: str) -> str:
    """Collapse case, punctuation and spacing so near-identical titles match."""
    return re.sub(r"[^\w\s]", "", text.lower()).strip()


def heading(title: str) -> None:
    print(f"\n{title}\n{'-' * len(title)}")


async def load(session: AsyncSession) -> tuple[list[Topic], list[Question]]:
    """Every topic and question, with the answers eagerly attached."""
    topics = list(
        await session.scalars(select(Topic).order_by(Topic.number, Topic.id))
    )
    questions = list(
        await session.scalars(
            select(Question).options(selectinload(Question.answers))
        )
    )
    return topics, questions


def report_topics(topics: list[Topic], questions: list[Question]) -> None:
    """Per-topic totals, plus topics that look duplicated or nearly empty."""
    counts = Counter(q.topic_id for q in questions)
    sources = defaultdict(Counter)
    for question in questions:
        sources[question.topic_id][question.source.value] += 1

    heading("Questions per topic")
    print(f"{'#':>3}  {'topic':<52} {'count':>6}  sources")
    for topic in topics:
        mix = dict(sources[topic.id])
        print(
            f"{topic.number:>3}  {topic.title_ru[:52]:<52} "
            f"{counts.get(topic.id, 0):>6}  {mix}"
        )
    print(f"\ntotal questions: {len(questions)}  topics: {len(topics)}")

    heading("Topics that look duplicated")
    by_title = defaultdict(list)
    for topic in topics:
        by_title[normalise(topic.title_ru)].append(topic)
    by_number = defaultdict(list)
    for topic in topics:
        by_number[topic.number].append(topic)

    found = False
    for title, group in by_title.items():
        if len(group) > 1:
            found = True
            print(f"  same title: {[(t.id, t.number, t.title_ru) for t in group]}")
    for number, group in by_number.items():
        if len(group) > 1:
            found = True
            print(f"  same number {number}: {[(t.id, t.title_ru) for t in group]}")
    # A title that merely contains another is the usual shape of an import
    # creating "ОБДЖ" beside an existing "ОБДЖ (расшифровка)".
    for outer in topics:
        for inner in topics:
            if outer.id >= inner.id:
                continue
            a, b = normalise(outer.title_ru), normalise(inner.title_ru)
            if a != b and (a.startswith(b) or b.startswith(a)):
                found = True
                print(
                    f"  one title is a prefix of the other: "
                    f"({outer.number}) {outer.title_ru!r} / "
                    f"({inner.number}) {inner.title_ru!r}"
                )
    if not found:
        print("  none")

    heading(f"Topics holding fewer than {THIN_TOPIC_THRESHOLD} questions")
    thin = [t for t in topics if counts.get(t.id, 0) < THIN_TOPIC_THRESHOLD]
    for topic in thin:
        print(f"  ({topic.number}) {topic.title_ru} — {counts.get(topic.id, 0)}")
    if not thin:
        print("  none")


def report_misfiling(topics: list[Topic], questions: list[Question]) -> None:
    """The same wording appearing under several topics.

    Repeated wording is normal on its own: dozens of picture questions share
    "Кому Вы уступите дорогу?" and differ only in the image. It is the spread
    across topics that is suspicious — one of those topics is usually wrong.
    """
    titles = {t.id: f"{t.number}. {t.title_ru}" for t in topics}
    by_text = defaultdict(list)
    for question in questions:
        by_text[question.text_ru.strip()].append(question)

    spread = {
        text: group
        for text, group in by_text.items()
        if len({q.topic_id for q in group}) > 1
    }

    heading("Same wording filed under several topics")
    print(f"  {len(spread)} wordings affected\n")
    for text, group in sorted(
        spread.items(), key=lambda kv: -len({q.topic_id for q in kv[1]})
    )[:EXAMPLES]:
        counts = Counter(q.topic_id for q in group)
        print(f"  {text[:88]}")
        for topic_id, count in counts.most_common():
            print(f"      {count:>3} x  {titles.get(topic_id, topic_id)}")
        print()


def report_integrity(questions: list[Question]) -> None:
    """Rows that cannot be rendered or answered correctly, whatever the topic."""
    heading("Structural integrity")

    no_correct = [q for q in questions if sum(a.is_correct for a in q.answers) != 1]
    too_few = [q for q in questions if len(q.answers) < 2]
    blank = [q for q in questions if not q.text_ru.strip()]
    no_kz = [q for q in questions if not (q.text_kz or "").strip()]
    no_expl = [q for q in questions if not (q.explanation_ru or "").strip()]

    checks = [
        ("questions without exactly one correct answer", no_correct),
        ("questions with fewer than two options", too_few),
        ("questions with empty Russian text", blank),
        ("questions with no Kazakh text", no_kz),
        ("questions with no Russian explanation", no_expl),
    ]
    for label, rows in checks:
        print(f"  {label}: {len(rows)}")
        for question in rows[:EXAMPLES]:
            print(f"      id={question.id}  {question.text_ru[:70]}")

    spread = Counter(len(q.answers) for q in questions)
    print(f"  option counts: {dict(sorted(spread.items()))}")


async def main() -> None:
    async with AsyncSessionLocal() as session:
        topics, questions = await load(session)

    if not questions:
        print("No questions in the database — is this the right DATABASE_URL?")
        return

    report_topics(topics, questions)
    report_misfiling(topics, questions)
    report_integrity(questions)

    heading("Next step")
    print(
        "  Compare the per-topic totals above with the official curriculum.\n"
        "  A topic whose count is far off, or one flagged as duplicated, is\n"
        "  where a wrong import shows up first."
    )


if __name__ == "__main__":
    asyncio.run(main())
