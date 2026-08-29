from __future__ import annotations

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import ValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.request_ids import json_error
from app.config import get_settings

_TRACE_MARKERS = ("Traceback (most recent call last)", 'File "', "  File ")


class ApiError(Exception):
    """Typed public HTTP error. Handlers must not attach stack traces."""

    def __init__(self, status_code: int, error_code: str, message: str) -> None:
        self.status_code = status_code
        self.error_code = error_code
        self.message = message
        super().__init__(message)


def _request_id_of(request: Request) -> str | None:
    value = getattr(request.state, "request_id", None)
    return value if isinstance(value, str) else None


def _public_validation_message(exc: RequestValidationError | ValidationError) -> str:
    errors = exc.errors()
    if not errors:
        return "Request validation failed."
    first = errors[0]
    loc_parts = [str(part) for part in first.get("loc", ()) if part not in {"body"}]
    location = ".".join(loc_parts)
    msg = str(first.get("msg", "invalid"))
    if location:
        return f"Invalid request ({location}): {msg}"
    return f"Invalid request: {msg}"


def _contains_traceback(text: str) -> bool:
    return any(marker in text for marker in _TRACE_MARKERS)


async def api_error_handler(request: Request, exc: ApiError) -> JSONResponse:
    return json_error(
        exc.status_code,
        error_code=exc.error_code,
        message=exc.message,
        request_id=_request_id_of(request),
    )


async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    detail = exc.detail
    if isinstance(detail, str) and not _contains_traceback(detail):
        message = detail
    else:
        message = "Request failed."
    code = "not_found" if exc.status_code == 404 else "http_error"
    return json_error(
        exc.status_code,
        error_code=code,
        message=message,
        request_id=_request_id_of(request),
    )


async def validation_exception_handler(
    request: Request, exc: RequestValidationError | ValidationError
) -> JSONResponse:
    return json_error(
        422,
        error_code="validation_error",
        message=_public_validation_message(exc),
        request_id=_request_id_of(request),
    )


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    import logging

    logger = logging.getLogger("app.api")
    logger.exception(
        "unhandled_error",
        extra={
            "event": "unhandled_error",
            "path": str(request.url.path),
            "request_id": _request_id_of(request),
            "error_type": type(exc).__name__,
        },
    )
    settings = get_settings()
    if settings.app_env == "development":
        message = f"{type(exc).__name__}: {exc}"
        if _contains_traceback(message):
            message = "An unexpected error occurred."
    else:
        message = "An unexpected error occurred."
    return json_error(
        500,
        error_code="internal_error",
        message=message,
        request_id=_request_id_of(request),
    )
