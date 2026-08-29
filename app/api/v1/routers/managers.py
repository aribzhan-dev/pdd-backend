"""Manager accounts — administrators only."""
from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query, status

from app.api.deps import AdminDep, DbSession
from app.schemas.common import Message, Page
from app.schemas.user import ManagerCreate, ManagerUpdate, UserBrief
from app.services.user import UserService

router = APIRouter(prefix="/managers", tags=["managers"])


@router.post(
    "", response_model=UserBrief, status_code=status.HTTP_201_CREATED
)
async def create_manager(
    payload: ManagerCreate, admin: AdminDep, session: DbSession
) -> UserBrief:
    """Issue a manager account."""
    return await UserService(session).create_manager(admin, payload)


@router.get("", response_model=Page[UserBrief])
async def list_managers(
    admin: AdminDep,
    session: DbSession,
    search: Annotated[str | None, Query(max_length=100)] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> Page[UserBrief]:
    """List manager accounts."""
    return await UserService(session).list_managers(
        admin, search=search, page=page, limit=limit
    )


@router.patch("/{manager_id}", response_model=UserBrief)
async def update_manager(
    manager_id: int, payload: ManagerUpdate, admin: AdminDep, session: DbSession
) -> UserBrief:
    """Edit a manager account."""
    return await UserService(session).update_manager(admin, manager_id, payload)


@router.delete("/{manager_id}", response_model=Message)
async def delete_manager(
    manager_id: int, admin: AdminDep, session: DbSession
) -> Message:
    """Remove a manager account."""
    await UserService(session).delete_manager(admin, manager_id)
    return Message(detail="Менеджер удалён")
