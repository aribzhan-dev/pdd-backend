"""Question model.

Media is referenced through `media_assets` rather than stored as a path, so a
clip shared by hundreds of questions exists once. `content_hash` is a separate,
text-based fingerprint used to merge the same question arriving from two
different source platforms.
"""
from __future__ import annotations

import enum
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, Enum, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin

if TYPE_CHECKING:
    from app.models.answer import Answer
    from app.models.media_asset import MediaAsset
    from app.models.topic import Topic


class ContentSource(str, enum.Enum):
    """Which platform a question was imported from."""

    OTAN = "otan"
    PDDTEST = "pddtest"
    MANUAL = "manual"


class Question(Base, TimestampMixin):
    """A single question with its localised text, media and answer options."""

    __tablename__ = "questions"
    __table_args__ = (Index("ix_questions_topic_order", "topic_id", "order"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    topic_id: Mapped[int] = mapped_column(
        ForeignKey("topics.id", ondelete="CASCADE"), index=True, nullable=False
    )

    # --- Localised content ---
    text_ru: Mapped[str] = mapped_column(Text, nullable=False)
    text_kz: Mapped[str | None] = mapped_column(Text)
    explanation_ru: Mapped[str | None] = mapped_column(Text)
    explanation_kz: Mapped[str | None] = mapped_column(Text)

    # --- Media (deduplicated assets) ---
    image_id: Mapped[int | None] = mapped_column(
        ForeignKey("media_assets.id", ondelete="SET NULL")
    )
    situation_video_id: Mapped[int | None] = mapped_column(
        ForeignKey("media_assets.id", ondelete="SET NULL")
    )
    explanation_video_ru_id: Mapped[int | None] = mapped_column(
        ForeignKey("media_assets.id", ondelete="SET NULL")
    )
    explanation_video_kz_id: Mapped[int | None] = mapped_column(
        ForeignKey("media_assets.id", ondelete="SET NULL")
    )

    # --- Provenance and merge key ---
    source: Mapped[ContentSource] = mapped_column(
        Enum(ContentSource, native_enum=False, length=20),
        default=ContentSource.OTAN,
        nullable=False,
    )
    source_id: Mapped[str | None] = mapped_column(String(64), index=True)
    #: Normalised fingerprint of the question text plus its answers; used to
    #: recognise the same question across platforms.
    content_hash: Mapped[str] = mapped_column(String(64), index=True, nullable=False)

    is_exam_only: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    topic: Mapped["Topic"] = relationship(back_populates="questions")
    answers: Mapped[list["Answer"]] = relationship(
        back_populates="question",
        cascade="all, delete-orphan",
        order_by="Answer.order",
        lazy="selectin",
    )

    image: Mapped["MediaAsset | None"] = relationship(foreign_keys=[image_id])
    situation_video: Mapped["MediaAsset | None"] = relationship(
        foreign_keys=[situation_video_id]
    )
    explanation_video_ru: Mapped["MediaAsset | None"] = relationship(
        foreign_keys=[explanation_video_ru_id]
    )
    explanation_video_kz: Mapped["MediaAsset | None"] = relationship(
        foreign_keys=[explanation_video_kz_id]
    )
