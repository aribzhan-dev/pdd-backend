from __future__ import annotations

from fastapi import APIRouter

from app.api.v1.routers import auth, content, managers, quiz, students

api_router = APIRouter()
api_router.include_router(auth.router)
api_router.include_router(managers.router)
api_router.include_router(students.router)
api_router.include_router(content.router)
api_router.include_router(quiz.router)
