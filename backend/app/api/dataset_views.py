"""Build dataset API views from deterministic inspection and data tools. No forecast math."""

from __future__ import annotations

from datetime import datetime
from math import isfinite

import pandas as pd

from app.api.schemas import (
    DatasetResponse,
    DiagnosticSummary,
    MissingPeriodView,
    SeriesPoint,
)
from app.api.store import FileStore
from app.data.anomalies import diagnose_outliers, diagnose_rolling_anomalies
from app.data.schemas import TIMESTAMP_COL, VALUE_COL, DiagnosticResult
from app.data.seasonality import diagnose_seasonality, period_from_frequency
from app.data.structural_breaks import diagnose_structural_breaks
from app.data.validator import inspect_csv


def metadata_only(record: DatasetResponse) -> DatasetResponse:
    return record.model_copy(
        update={
            "points": [],
            "missing_periods": [],
            "anomalies": None,
            "seasonality": None,
            "structural_break": None,
        }
    )


def enrich_dataset_from_store(store: FileStore, record: DatasetResponse) -> DatasetResponse:
    csv_path = store.dataset_csv_path(record.id)
    inspection = inspect_csv(csv_path)
    if not inspection.is_valid() or inspection.profile is None:
        return record
    derived = inspection.derived
    profile = inspection.profile
    frequency = profile.frequency.frequency
    period = period_from_frequency(frequency) if frequency else None
    timestamps = derived[TIMESTAMP_COL]
    values = derived[VALUE_COL]
    outliers = diagnose_outliers(values, timestamps)
    rolling = diagnose_rolling_anomalies(values, timestamps)
    anomalies = (
        outliers
        if outliers.detected or outliers.evidence.n_flagged >= rolling.evidence.n_flagged
        else rolling
    )
    if rolling.detected and not outliers.detected:
        anomalies = rolling
    seasonality = diagnose_seasonality(values, timestamps, period=period, frequency=frequency)
    breaks = diagnose_structural_breaks(values, timestamps)
    return record.model_copy(
        update={
            "points": _points(derived),
            "missing_periods": [
                MissingPeriodView(
                    start=item.start,
                    end=item.end,
                    n_steps=item.n_steps,
                    series_id=item.series_id,
                )
                for item in profile.missing_periods
            ],
            "anomalies": _summary(anomalies),
            "seasonality": _summary(seasonality),
            "structural_break": _summary(breaks),
        }
    )


def _points(derived: pd.DataFrame) -> list[SeriesPoint]:
    points: list[SeriesPoint] = []
    for timestamp, value in zip(derived[TIMESTAMP_COL], derived[VALUE_COL], strict=True):
        if pd.isna(timestamp):
            continue
        ts = timestamp.to_pydatetime() if hasattr(timestamp, "to_pydatetime") else timestamp
        if not isinstance(ts, datetime):
            continue
        numeric: float | None
        if pd.isna(value):
            numeric = None
        else:
            try:
                numeric = float(value)
                if not isfinite(numeric):
                    numeric = None
            except (TypeError, ValueError):
                numeric = None
        points.append(SeriesPoint(timestamp=ts, value=numeric))
    return points


def _summary(result: DiagnosticResult) -> DiagnosticSummary:
    return DiagnosticSummary(
        name=result.name,
        detected=result.detected,
        confidence=result.confidence,
        strength=result.strength,
        summary=result.evidence.summary,
        n_flagged=result.evidence.n_flagged,
        limitations=list(result.limitations),
    )
