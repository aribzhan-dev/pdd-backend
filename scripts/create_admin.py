from __future__ import annotations

import argparse
import asyncio
import sys

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.db import AsyncSessionLocal
from app.core.security import hash_password
from app.enums.role import UserRole
from app.models.user import IIN_LENGTH, User
from app.repositories.user import UserRepository

settings = get_settings()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create the bootstrap admin")
    parser.add_argument("--iin", default=settings.ADMIN_IIN)
    parser.add_argument("--password", default=settings.ADMIN_PASSWORD)
    parser.add_argument("--name", default=settings.ADMIN_NAME)
    parser.add_argument("--surname", default=settings.ADMIN_SURNAME)
    return parser.parse_args()


def validate(args: argparse.Namespace) -> str:
    """Return an error message, or an empty string when the input is usable."""
    if not args.iin or not args.password:
        return (
            "Set ADMIN_IIN and ADMIN_PASSWORD in .env, or pass --iin and "
            "--password on the command line."
        )
    if not (args.iin.isdigit() and len(args.iin) == IIN_LENGTH):
        return f"IIN must be exactly {IIN_LENGTH} digits, got {args.iin!r}."
    return ""


async def upsert_admin(session: AsyncSession, args: argparse.Namespace) -> str:
    """Create the administrator, or reset an existing account to admin."""
    users = UserRepository(session)
    existing = await users.get_by_iin(args.iin)

    if existing is not None:
        existing.password_hash = hash_password(args.password)
        existing.role = UserRole.ADMIN
        existing.is_active = True
        await session.commit()
        return f"Updated existing account {args.iin} — password reset, role admin."

    users.add(
        User(
            iin=args.iin,
            password_hash=hash_password(args.password),
            name=args.name,
            surname=args.surname,
            role=UserRole.ADMIN,
        )
    )
    await session.commit()
    return f"Created administrator {args.iin} ({args.surname} {args.name})."


async def main() -> int:
    """Entry point; returns the process exit code."""
    args = parse_args()
    problem = validate(args)
    if problem:
        print(f"error: {problem}", file=sys.stderr)
        return 1

    async with AsyncSessionLocal() as session:
        print(await upsert_admin(session, args))
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
