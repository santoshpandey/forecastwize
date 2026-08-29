"""Load a stored dataset for adapters. No forecast math."""

from __future__ import annotations

from io import BytesIO

import pandas as pd

from app.api.errors import ApiError
from app.api.schemas import DatasetResponse
from app.api.store import FileStore
from app.data.schemas import (
    CONTEXT_COL,
    EVENT_COL,
    SERIES_ID_COL,
    TIMESTAMP_COL,
    VALUE_COL,
    SeriesValidationError,
)
from app.data.validator import inspect_csv


def inspect_csv_bytes(content: bytes):
    try:
        return inspect_csv(BytesIO(content))
    except SeriesValidationError as exc:
        first = exc.issues[0] if exc.issues else None
        message = first.message if first is not None else "CSV could not be parsed."
        raise ApiError(422, "invalid_csv", message) from exc


def load_dataset_frame(store: FileStore, dataset_id: str) -> tuple[DatasetResponse, pd.DataFrame]:
    record = store.get_dataset(dataset_id)
    csv_path = store.dataset_csv_path(dataset_id)
    if not csv_path.is_file():
        raise ApiError(404, "not_found", "Dataset was not found.")
    inspection = inspect_csv(csv_path)
    if not inspection.is_valid() or inspection.profile is None:
        raise ApiError(422, "invalid_csv", "Stored dataset failed validation.")
    derived = inspection.derived
    if SERIES_ID_COL in derived.columns:
        n_series = int(derived[SERIES_ID_COL].astype(str).nunique())
        if n_series > 1:
            raise ApiError(
                422,
                "multiple_series",
                "Datasets with more than one series_id are not supported.",
            )
    return record, derived


def resolve_frequency(record: DatasetResponse, requested: str | None) -> str:
    if requested is not None:
        return requested
    if record.frequency:
        return record.frequency
    raise ApiError(
        422,
        "frequency_required",
        "Frequency is unresolved on this dataset; pass an explicit frequency.",
    )


def series_columns(
    frame: pd.DataFrame,
) -> tuple[pd.Series, pd.Series, pd.Series | None, pd.Series | None]:
    timestamps = frame[TIMESTAMP_COL]
    values = frame[VALUE_COL]
    events = frame[EVENT_COL] if EVENT_COL in frame.columns else None
    context = frame[CONTEXT_COL] if CONTEXT_COL in frame.columns else None
    return timestamps, values, events, context


def inspect_uploaded_frame(content: bytes):
    inspection = inspect_csv_bytes(content)
    if not inspection.is_valid() or inspection.profile is None:
        errors = inspection.error_issues()
        first = errors[0] if errors else None
        message = first.message if first is not None else "CSV is not a valid series."
        raise ApiError(422, "invalid_csv", message)
    return inspection
