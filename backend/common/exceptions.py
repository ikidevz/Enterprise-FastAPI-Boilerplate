from __future__ import annotations

from fastapi import HTTPException, status


class DomainError(Exception):
    """Base class for domain-layer errors."""

    def __init__(self, message: str, *, error_code: str | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.error_code = error_code


class ApplicationError(DomainError):
    """Base class for application-layer errors."""


class DuplicateResourceError(DomainError):
    def __init__(self, resource: str, *, message: str | None = None) -> None:
        detail = message or f"{resource} already exists"
        super().__init__(detail, error_code=f"duplicate_{resource}")
        self.resource = resource


class NotFoundError(DomainError):
    def __init__(self, resource: str, *, message: str | None = None) -> None:
        detail = message or f"{resource} not found"
        super().__init__(detail, error_code="not_found")
        self.resource = resource


class UnauthorizedError(DomainError):
    def __init__(self, message: str = "Unauthorized", *, error_code: str = "unauthorized") -> None:
        super().__init__(message, error_code=error_code)


class ForbiddenError(DomainError):
    def __init__(self, message: str = "Forbidden", *, error_code: str = "forbidden") -> None:
        super().__init__(message, error_code=error_code)


class ValidationError(DomainError):
    def __init__(self, message: str, *, error_code: str = "validation_error") -> None:
        super().__init__(message, error_code=error_code)


class ConflictError(DomainError):
    def __init__(self, message: str, *, error_code: str = "conflict") -> None:
        super().__init__(message, error_code=error_code)


class DomainHTTPException(HTTPException):
    def __init__(self, error: DomainError, *, status_code: int) -> None:
        super().__init__(status_code=status_code, detail={
            "message": str(error), "error_code": error.error_code, "detail": str(error)})
        self.error = error


def to_http_exception(error: DomainError) -> HTTPException:
    status_code = status.HTTP_400_BAD_REQUEST
    if isinstance(error, NotFoundError):
        status_code = status.HTTP_404_NOT_FOUND
    elif isinstance(error, UnauthorizedError):
        status_code = status.HTTP_401_UNAUTHORIZED
    elif isinstance(error, ForbiddenError):
        status_code = status.HTTP_403_FORBIDDEN
    elif isinstance(error, ConflictError):
        status_code = status.HTTP_409_CONFLICT
    elif isinstance(error, ValidationError):
        status_code = status.HTTP_422_UNPROCESSABLE_ENTITY

    return DomainHTTPException(error, status_code=status_code)
