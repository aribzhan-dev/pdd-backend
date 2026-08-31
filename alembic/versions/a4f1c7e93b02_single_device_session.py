"""single device session

Adds `users.session_id`. Every login writes a fresh value and stamps it into
the issued tokens; a token whose value no longer matches is refused, which is
what limits an account to one device at a time.

Nullable on purpose: accounts that existed before this change have no session
until their next login, and the API treats a null as "no restriction yet"
rather than locking those users out.

Revision ID: a4f1c7e93b02
Revises: de73f7279eb4
Create Date: 2026-08-31
"""
from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a4f1c7e93b02"
down_revision: str | None = "de73f7279eb4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("users", sa.Column("session_id", sa.String(length=36), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "session_id")
