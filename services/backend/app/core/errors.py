from __future__ import annotations

from typing import Any


class AppError(Exception):
    def __init__(
        self,
        message: str,
        *,
        status_code: int = 500,
        code: str = "internal_error",
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.code = code
        self.details = details or {}


class ValidationAppError(AppError):
    def __init__(self, message: str, *, details: dict[str, Any] | None = None) -> None:
        super().__init__(message, status_code=400, code="validation_error", details=details)


class AuthAppError(AppError):
    def __init__(self, message: str, *, status_code: int = 401, code: str = "auth_error") -> None:
        super().__init__(message, status_code=status_code, code=code)


class PermissionAppError(AppError):
    def __init__(self, message: str) -> None:
        super().__init__(message, status_code=403, code="permission_denied")


class NotFoundAppError(AppError):
    def __init__(self, message: str) -> None:
        super().__init__(message, status_code=404, code="not_found")


class ConflictAppError(AppError):
    def __init__(self, message: str) -> None:
        super().__init__(message, status_code=409, code="conflict")


class ExternalServiceAppError(AppError):
    def __init__(
        self,
        message: str,
        *,
        service: str,
        status_code: int = 503,
        details: dict[str, Any] | None = None,
    ) -> None:
        payload = {"service": service}
        if details:
            payload.update(details)
        super().__init__(message, status_code=status_code, code="external_service_error", details=payload)

