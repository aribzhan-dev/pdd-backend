"""quiz session remembers which part of a topic it covered

Long topics are offered in parts, and the catalogue scores each part
separately. That needs the session to remember which part it ran; existing
rows covered their topic whole, which is what NULL means here.

Revision ID: c71f04ae5d19
Revises: a4f1c7e93b02
Create Date: 2026-09-24 00:00:00.000000
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c71f04ae5d19"
down_revision: str | None = "a4f1c7e93b02"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "quiz_sessions", sa.Column("topic_part", sa.Integer(), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("quiz_sessions", "topic_part")
