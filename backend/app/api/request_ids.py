from __future__ import annotations

from fastapi import Request
from fastapi.responses import JSONResponse

from app.request_context import set_request_id
from app.schemas import PublicErrorResponse

REQUEST_ID_HEADER = "X-Request-ID"
_MAX_REQUEST_ID_LEN = 128
_ALLOWED = set("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789._-")


def is_valid_request_id(value: str) -> bool:
    if not value or len(value) > _MAX_REQUEST_ID_LEN:
        return False
    return all(char in _ALLOWED for char in value)


def new_request_id() -> str:
    from uuid import uuid4

    return str(uuid4())


def resolve_request_id(header_value: str | None) -> str:
    candidate = (header_value or "").strip()
    if is_valid_request_id(candidate):
        return candidate
    return new_request_id()


async def request_id_middleware(request: Request, call_next):  # type: ignore[no-untyped-def]
    request_id = resolve_request_id(request.headers.get(REQUEST_ID_HEADER))
    request.state.request_id = request_id
    set_request_id(request_id)
    try:
        response = await call_next(request)
    finally:
        set_request_id(None)
    response.headers[REQUEST_ID_HEADER] = request_id
    return response


def public_error_body(*, error_code: str, message: str, request_id: str | None) -> dict[str, str]:
    return PublicErrorResponse(
        error_code=error_code,
        message=message,
        request_id=request_id,
    ).model_dump()


def json_error(
    status_code: int,
    *,
    error_code: str,
    message: str,
    request_id: str | None,
) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content=public_error_body(error_code=error_code, message=message, request_id=request_id),
    )
