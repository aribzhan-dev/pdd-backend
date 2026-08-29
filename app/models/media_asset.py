"""Deduplicated media files.

The source export stores the same clip many times over — one placeholder alone
appeared 190 times. Files are therefore keyed by content hash: identical bytes
collapse into a single row and a single file on disk, and every question that
needs that clip points at the same asset.
"""
from __future__ import annotations

import enum

from sqlalchemy import BigInteger, Enum, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin

#: Length of a hex-encoded SHA-256 digest.
SHA256_HEX_LENGTH = 64


class MediaKind(str, enum.Enum):
    """What the asset is used for."""

    SITUATION = "situation"
    EXPLANATION = "explanation"
    IMAGE = "image"


class MediaAsset(Base, TimestampMixin):
    """One unique file, referenced by any number of questions."""

    __tablename__ = "media_assets"

    id: Mapped[int] = mapped_column(primary_key=True)

    #: SHA-256 of the file contents — the deduplication key.
    sha256: Mapped[str] = mapped_column(
        String(SHA256_HEX_LENGTH), unique=True, index=True, nullable=False
    )
    #: Path relative to MEDIA_ROOT of the single retained copy.
    rel_path: Mapped[str] = mapped_column(String(512), nullable=False)
    kind: Mapped[MediaKind] = mapped_column(
        Enum(MediaKind, native_enum=False, length=20), nullable=False
    )
    byte_size: Mapped[int] = mapped_column(BigInteger, nullable=False)
    content_type: Mapped[str | None] = mapped_column(String(100))

    #: How many source files collapsed into this asset (1 = never duplicated).
    duplicate_count: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
