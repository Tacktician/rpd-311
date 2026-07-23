"""Typed application error + the shared RPD 311 error shape."""
from __future__ import annotations


class AppError(Exception):
    """Raised by handlers; serialized into { error, message, requestId, details }."""

    def __init__(
        self,
        status_code: int,
        code: str,
        message: str,
        details: list[dict] | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.details = details or []


def unauthorized(message: str) -> AppError:
    return AppError(401, "UNAUTHORIZED", message)


def not_found(code: str, message: str) -> AppError:
    return AppError(404, code, message)


def conflict(code: str, message: str) -> AppError:
    return AppError(409, code, message)
