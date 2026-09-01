"""Domain errors mapped to HTTP responses by the API layer.

Messages are user-facing and therefore written in Russian; the identifiers
stay English like the rest of the code.
"""
from __future__ import annotations


class AppError(Exception):
    """Base class for expected, reportable failures."""

    status_code: int = 400
    message: str = "Ошибка запроса"

    def __init__(self, message: str | None = None) -> None:
        self.message = message or self.message
        super().__init__(self.message)


class InvalidCredentialsError(AppError):
    """Wrong IIN or password."""

    status_code = 401
    message = "Неверный ИИН или пароль"


class TooManyAttemptsError(AppError):
    """Too many failed sign-ins from one address; it is temporarily locked."""

    status_code = 429
    message = "Слишком много попыток входа. Повторите позже"

    def __init__(self, retry_after: int, message: str | None = None) -> None:
        #: Seconds until the caller may try again; surfaced as a Retry-After header.
        self.retry_after = retry_after
        super().__init__(message)


class AccessExpiredError(AppError):
    """The student's access window has closed."""

    status_code = 403
    message = "Срок доступа истёк. Обратитесь к администратору"


class AccountInactiveError(AppError):
    """The account exists but is not allowed to sign in."""

    status_code = 403
    message = "Аккаунт неактивен. Обратитесь к администратору"


class SessionSupersededError(AppError):
    """The account signed in somewhere else, so this device is signed out."""

    status_code = 401
    message = "Вход выполнен на другом устройстве. Войдите заново"


class PermissionDeniedError(AppError):
    """The caller's role does not allow this action."""

    status_code = 403
    message = "Недостаточно прав для выполнения действия"


class NotFoundError(AppError):
    """The requested record does not exist."""

    status_code = 404
    message = "Запись не найдена"


class DuplicateIINError(AppError):
    """Another account already uses this IIN."""

    status_code = 409
    message = "Пользователь с таким ИИН уже существует"


class QuizStateError(AppError):
    """The quiz session cannot accept this operation."""

    status_code = 409
    message = "Недопустимое действие для этой сессии"
