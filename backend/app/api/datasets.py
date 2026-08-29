"""Dataset HTTP adapter. Validates and stores CSV; does not forecast."""

from __future__ import annotations

import json
import logging

from fastapi import APIRouter, Depends, Request

from app.api.dataset_views import enrich_dataset_from_store, metadata_only
from app.api.deps import get_app_settings, get_store
from app.api.errors import ApiError
from app.api.ids import new_prefixed_id, require_resource_id, sanitize_upload_filename
from app.api.schemas import DatasetCreateRequest, DatasetResponse
from app.api.series_io import inspect_uploaded_frame
from app.api.store import FileStore
from app.config import Settings
from app.time_utils import utc_now

router = APIRouter(tags=["datasets"])
logger = logging.getLogger(__name__)

_ALLOWED_UPLOAD_TYPES = frozenset(
    {
        "text/csv",
        "text/plain",
        "application/csv",
        "application/octet-stream",
        "",
    }
)


def _check_size(n_bytes: int, settings: Settings) -> None:
    if n_bytes > settings.max_upload_bytes:
        raise ApiError(
            413,
            "payload_too_large",
            f"Upload exceeds the maximum of {settings.max_upload_bytes} bytes.",
        )


def require_upload_content_length(request: Request, settings: Settings) -> None:
    """Reject uploads that omit Content-Length or declare more than the cap."""
    raw = request.headers.get("content-length")
    if raw is None or raw.strip() == "":
        raise ApiError(
            411,
            "length_required",
            "Content-Length is required for uploads.",
        )
    try:
        declared = int(raw)
    except ValueError as exc:
        raise ApiError(400, "invalid_content_length", "Content-Length is invalid.") from exc
    if declared < 0:
        raise ApiError(400, "invalid_content_length", "Content-Length is invalid.")
    _check_size(declared, settings)


async def _read_upload_capped(upload: object, settings: Settings) -> bytes:
    chunks: list[bytes] = []
    total = 0
    read = getattr(upload, "read", None)
    if read is None:
        raise ApiError(422, "validation_error", "multipart field 'file' is required.")
    while True:
        chunk = await read(64 * 1024)
        if not chunk:
            break
        if not isinstance(chunk, bytes):
            chunk = bytes(chunk)
        total += len(chunk)
        _check_size(total, settings)
        chunks.append(chunk)
    return b"".join(chunks)


async def _read_json_body_capped(request: Request, settings: Settings) -> bytes:
    chunks: list[bytes] = []
    total = 0
    async for chunk in request.stream():
        total += len(chunk)
        _check_size(total, settings)
        chunks.append(chunk)
    return b"".join(chunks)


def _dataset_from_csv(*, filename: str, content: bytes, settings: Settings) -> DatasetResponse:
    _check_size(len(content), settings)
    safe_name = sanitize_upload_filename(filename)
    inspection = inspect_uploaded_frame(content)
    profile = inspection.profile
    assert profile is not None
    stats = profile.statistics
    warnings = [item for item in inspection.issues if item.severity == "warning"]
    dataset_id = new_prefixed_id("ds")
    return DatasetResponse(
        id=dataset_id,
        filename=safe_name,
        created_at=utc_now(),
        n_rows=stats.n_rows,
        n_missing_values=stats.n_missing_values,
        frequency=profile.frequency.frequency,
        frequency_confidence=profile.frequency.confidence,
        timestamp_start=stats.start,
        timestamp_end=stats.end,
        has_series_id=profile.has_series_id,
        has_context=profile.has_context,
        has_event=profile.has_event,
        extra_columns=list(profile.extra_columns),
        warnings=warnings,
    )


@router.post("/datasets", response_model=DatasetResponse, status_code=201)
async def create_dataset(
    request: Request,
    store: FileStore = Depends(get_store),
    settings: Settings = Depends(get_app_settings),
) -> DatasetResponse:
    require_upload_content_length(request, settings)
    content_type = (request.headers.get("content-type") or "").lower()
    if content_type.startswith("multipart/form-data"):
        try:
            form = await request.form()
        except AssertionError as exc:
            raise ApiError(
                503,
                "upload_unavailable",
                "Multipart uploads are not available in this process.",
            ) from exc
        upload = form.get("file")
        if upload is None or not hasattr(upload, "read"):
            raise ApiError(422, "validation_error", "multipart field 'file' is required.")
        declared = (getattr(upload, "content_type", None) or "").split(";")[0].strip().lower()
        if declared not in _ALLOWED_UPLOAD_TYPES:
            raise ApiError(
                415,
                "unsupported_media_type",
                "Upload Content-Type must be CSV or plain text.",
            )
        raw_name = getattr(upload, "filename", None) or "upload.csv"
        content = await _read_upload_capped(upload, settings)
        record = _dataset_from_csv(filename=str(raw_name), content=content, settings=settings)
    elif "application/json" in content_type:
        raw_body = await _read_json_body_capped(request, settings)
        try:
            payload = json.loads(raw_body)
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise ApiError(422, "validation_error", "Request body is not valid JSON.") from exc
        body = DatasetCreateRequest.model_validate(payload)
        content = body.csv_text.encode("utf-8")
        record = _dataset_from_csv(filename=body.filename, content=content, settings=settings)
    else:
        raise ApiError(
            415,
            "unsupported_media_type",
            "Use application/json or multipart/form-data.",
        )

    store.put_dataset(metadata_only(record), content)
    view = enrich_dataset_from_store(store, record)
    logger.info(
        "dataset_created",
        extra={
            "event": "dataset_created",
            "dataset_id": record.id,
            "upload_filename": record.filename,
            "n_rows": record.n_rows,
            "n_missing_values": record.n_missing_values,
        },
    )
    return view


@router.get("/datasets/{dataset_id}", response_model=DatasetResponse)
def get_dataset(dataset_id: str, store: FileStore = Depends(get_store)) -> DatasetResponse:
    require_resource_id(dataset_id)
    record = store.get_dataset(dataset_id)
    view = enrich_dataset_from_store(store, record)
    logger.info(
        "dataset_fetched",
        extra={"event": "dataset_fetched", "dataset_id": dataset_id},
    )
    return view
