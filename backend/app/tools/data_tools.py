"""Deterministic data-diagnostic tools. Agents request these; they do not invent stats.

Does not fit models, emit yhat, or modify the caller's series. No FastAPI. No LLM.
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
from pydantic import BaseModel, ConfigDict, Field

from app.data.anomalies import diagnose_outliers, diagnose_rolling_anomalies
from app.data.schemas import TIMESTAMP_COL, VALUE_COL, DiagnosticResult, SeriesProfile
from app.data.seasonality import diagnose_seasonality, diagnose_trend
from app.data.structural_breaks import diagnose_structural_breaks
from app.data.validator import SeriesInspection, inspect_frame
from app.forecasting.base import ForecastInterfaceError

INSPECT_SERIES = "inspect_series"
DIAGNOSE_QUALITY = "diagnose_quality"
DIAGNOSE_OUTLIERS = "diagnose_outliers"
DIAGNOSE_ROLLING_ANOMALIES = "diagnose_rolling_anomalies"
DIAGNOSE_TREND = "diagnose_trend"
DIAGNOSE_SEASONALITY = "diagnose_seasonality"
DIAGNOSE_STRUCTURAL_BREAKS = "diagnose_structural_breaks"

DATA_TOOL_NAMES = (
    INSPECT_SERIES,
    DIAGNOSE_QUALITY,
    DIAGNOSE_OUTLIERS,
    DIAGNOSE_ROLLING_ANOMALIES,
    DIAGNOSE_TREND,
    DIAGNOSE_SEASONALITY,
    DIAGNOSE_STRUCTURAL_BREAKS,
)

JsonObject = dict[str, Any]


class DataToolSpec(BaseModel):
    """Allowlisted diagnostic arguments. Unknown fields are rejected."""

    model_config = ConfigDict(extra="forbid")

    frequency: str | None = None
    seasonal_period: int | None = None
    rolling_window: int = 7


class DataToolEnvelope(BaseModel):
    """Typed tool return. `payload` is JSON-ready; never a forecast."""

    model_config = ConfigDict(extra="forbid")

    tool_name: str
    ok: bool
    payload: JsonObject
    error_type: str | None = None
    error_message: str | None = None


class InspectToolResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    is_valid: bool
    n_rows: int
    n_missing_values: int | None = None
    n_duplicate_timestamps: int | None = None
    n_zeros: int | None = None
    n_negative: int | None = None
    frequency: str | None = None
    frequency_method: str | None = None
    frequency_confidence: str | None = None
    has_event: bool = False
    has_context: bool = False
    n_event_non_null: int = 0
    n_context_non_null: int = 0
    extra_columns: list[str] = Field(default_factory=list)
    issue_codes: list[str] = Field(default_factory=list)
    error_codes: list[str] = Field(default_factory=list)
    warning_codes: list[str] = Field(default_factory=list)
    missing_period_count: int = 0
    summary: str
    limitations: list[str] = Field(default_factory=list)


class QualityToolResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = "data_quality"
    detected: bool
    n_missing_values: int
    n_duplicate_timestamps: int
    n_zeros: int
    n_negative: int
    missing_period_count: int
    frequency_resolved: bool
    zero_share: float | None
    error_codes: list[str]
    warning_codes: list[str]
    has_event_column: bool
    has_context_column: bool
    n_event_non_null: int
    summary: str
    limitations: list[str]
    confidence: str


def reject_unknown_data_tool(name: str) -> None:
    if name not in DATA_TOOL_NAMES:
        allowed = ", ".join(DATA_TOOL_NAMES)
        msg = f"Unknown tool {name!r}. Approved data tools: {allowed}."
        raise ForecastInterfaceError(msg)


def run_named_data_tool(
    name: str,
    timestamps: pd.Series | pd.DatetimeIndex | None,
    values: pd.Series | np.ndarray | None,
    spec: DataToolSpec,
    *,
    inspection: SeriesInspection | None = None,
) -> DataToolEnvelope:
    """Dispatch one allowlisted diagnostic. Does not call an LLM or emit yhat."""
    reject_unknown_data_tool(name)
    if name == INSPECT_SERIES:
        return run_inspect_series_tool(timestamps, values)
    if name == DIAGNOSE_QUALITY:
        return run_quality_tool(timestamps, values, inspection=inspection)
    if name == DIAGNOSE_OUTLIERS:
        return _diagnostic_envelope(name, diagnose_outliers(values, timestamps))
    if name == DIAGNOSE_ROLLING_ANOMALIES:
        return _diagnostic_envelope(
            name,
            diagnose_rolling_anomalies(values, timestamps, window=spec.rolling_window),
        )
    if name == DIAGNOSE_TREND:
        return _diagnostic_envelope(name, diagnose_trend(values, timestamps))
    if name == DIAGNOSE_SEASONALITY:
        period = spec.seasonal_period
        frequency = spec.frequency
        return _diagnostic_envelope(
            name,
            diagnose_seasonality(values, timestamps, period=period, frequency=frequency),
        )
    if name == DIAGNOSE_STRUCTURAL_BREAKS:
        return _diagnostic_envelope(name, diagnose_structural_breaks(values, timestamps))
    msg = f"Unhandled approved tool {name!r}"
    raise ForecastInterfaceError(msg)


def run_inspect_series_tool(
    timestamps: pd.Series | pd.DatetimeIndex | None,
    values: pd.Series | np.ndarray | None,
) -> DataToolEnvelope:
    problem = input_problem(timestamps, values)
    if problem is not None:
        payload = InspectToolResult(
            is_valid=False,
            n_rows=0 if values is None else int(np.asarray(values).size),
            summary=problem,
            limitations=["Input rejected before profiling. Source arrays were not modified."],
            error_codes=["invalid_input"],
            issue_codes=["invalid_input"],
        ).model_dump(mode="json")
        return DataToolEnvelope(
            tool_name=INSPECT_SERIES,
            ok=False,
            payload=payload,
            error_type="InvalidInput",
            error_message=problem,
        )
    frame = _frame_from_arrays(timestamps, values)
    inspection = inspect_frame(frame)
    payload = inspect_result_from_inspection(inspection).model_dump(mode="json")
    return DataToolEnvelope(
        tool_name=INSPECT_SERIES,
        ok=inspection.is_valid(),
        payload=payload,
        error_type=None if inspection.is_valid() else "InspectionError",
        error_message=None
        if inspection.is_valid()
        else "; ".join(item.message for item in inspection.error_issues()),
    )


def run_quality_tool(
    timestamps: pd.Series | pd.DatetimeIndex | None,
    values: pd.Series | np.ndarray | None,
    *,
    inspection: SeriesInspection | None = None,
) -> DataToolEnvelope:
    if inspection is None:
        inspect_env = run_inspect_series_tool(timestamps, values)
        if not inspect_env.ok and inspect_env.error_type == "InvalidInput":
            quality = QualityToolResult(
                detected=True,
                n_missing_values=0,
                n_duplicate_timestamps=0,
                n_zeros=0,
                n_negative=0,
                missing_period_count=0,
                frequency_resolved=False,
                zero_share=None,
                error_codes=["invalid_input"],
                warning_codes=[],
                has_event_column=False,
                has_context_column=False,
                n_event_non_null=0,
                summary=inspect_env.error_message or "Invalid input.",
                limitations=[
                    "Quality was not scored on an invalid series. Data were not modified."
                ],
                confidence="high",
            )
            return DataToolEnvelope(
                tool_name=DIAGNOSE_QUALITY,
                ok=False,
                payload=quality.model_dump(mode="json"),
                error_type=inspect_env.error_type,
                error_message=inspect_env.error_message,
            )
        frame = _frame_from_arrays(timestamps, values)
        inspection = inspect_frame(frame)
    quality = quality_from_inspection(inspection)
    return DataToolEnvelope(
        tool_name=DIAGNOSE_QUALITY,
        ok=True,
        payload=quality.model_dump(mode="json"),
    )


def inspect_series(timestamps: object, values: object) -> SeriesInspection:
    """Build a frame and inspect it. Does not mutate the caller's objects."""
    problem = input_problem(timestamps, values)
    if problem is not None:
        msg = problem
        raise ForecastInterfaceError(msg)
    return inspect_frame(_frame_from_arrays(timestamps, values))


def input_problem(
    timestamps: pd.Series | pd.DatetimeIndex | None,
    values: pd.Series | np.ndarray | None,
) -> str | None:
    if values is None:
        return "values are required"
    try:
        y = np.asarray(values, dtype=float)
    except (TypeError, ValueError) as exc:
        return f"values are not numeric: {exc}"
    if y.ndim != 1:
        return "values must be one-dimensional"
    if y.size == 0:
        return "values are empty"
    if timestamps is None:
        return "timestamps are required"
    try:
        n_ts = len(timestamps)
    except TypeError:
        return "timestamps are required"
    if n_ts != y.size:
        return f"timestamps length {n_ts} != values length {y.size}"
    return None


def inspect_result_from_inspection(inspection: SeriesInspection) -> InspectToolResult:
    issues = inspection.issues
    error_codes = [item.code for item in issues if item.severity == "error"]
    warning_codes = [item.code for item in issues if item.severity == "warning"]
    profile = inspection.profile
    limitations = [
        "Inspection profiles a derived copy. The original frame is not modified.",
        "Event and context columns are reported only if present; none are invented.",
    ]
    if profile is None:
        n_rows = int(len(inspection.derived))
        return InspectToolResult(
            is_valid=False,
            n_rows=n_rows,
            issue_codes=[item.code for item in issues],
            error_codes=error_codes,
            warning_codes=warning_codes,
            summary="; ".join(item.message for item in inspection.error_issues())
            or "Inspection failed.",
            limitations=limitations,
        )
    stats = profile.statistics
    return InspectToolResult(
        is_valid=inspection.is_valid(),
        n_rows=stats.n_rows,
        n_missing_values=stats.n_missing_values,
        n_duplicate_timestamps=stats.n_duplicate_timestamps,
        n_zeros=stats.n_zeros,
        n_negative=stats.n_negative,
        frequency=profile.frequency.frequency,
        frequency_method=profile.frequency.method,
        frequency_confidence=profile.frequency.confidence,
        has_event=profile.has_event,
        has_context=profile.has_context,
        n_event_non_null=profile.n_event_non_null,
        n_context_non_null=profile.n_context_non_null,
        extra_columns=list(profile.extra_columns),
        issue_codes=[item.code for item in issues],
        error_codes=error_codes,
        warning_codes=warning_codes,
        missing_period_count=len(profile.missing_periods),
        summary=_inspect_summary(profile, error_codes, warning_codes),
        limitations=limitations,
    )


def quality_from_inspection(inspection: SeriesInspection) -> QualityToolResult:
    inspect_view = inspect_result_from_inspection(inspection)
    n_missing = inspect_view.n_missing_values or 0
    n_dup = inspect_view.n_duplicate_timestamps or 0
    n_zeros = inspect_view.n_zeros or 0
    n_neg = inspect_view.n_negative or 0
    n_rows = max(inspect_view.n_rows, 1)
    zero_share = n_zeros / n_rows if inspect_view.n_rows else None
    freq_ok = inspect_view.frequency is not None
    detected = bool(
        inspect_view.error_codes
        or n_missing
        or n_dup
        or inspect_view.missing_period_count
        or not freq_ok
    )
    parts: list[str] = []
    if inspect_view.error_codes:
        parts.append("error-severity validation issues: " + ", ".join(inspect_view.error_codes))
    if n_missing:
        parts.append(f"{n_missing} missing value(s)")
    if n_dup:
        parts.append(f"{n_dup} duplicate timestamp row(s)")
    if inspect_view.missing_period_count:
        parts.append(f"{inspect_view.missing_period_count} inferred gap period(s)")
    if not freq_ok:
        parts.append("frequency unresolved")
    if zero_share is not None and zero_share >= 0.3:
        parts.append(f"zero share {zero_share:.2f} (intermittent-demand risk)")
    if not parts:
        parts.append("No missing values, duplicates, or unresolved frequency in the profile.")
    limitations = [
        "Quality flags are descriptive. Values are not filled, clipped, or dropped.",
        "A present event column is not a causal explanation; labels are not invented.",
    ]
    confidence = "high" if inspect_view.error_codes else "medium"
    return QualityToolResult(
        detected=detected or (zero_share is not None and zero_share >= 0.3),
        n_missing_values=n_missing,
        n_duplicate_timestamps=n_dup,
        n_zeros=n_zeros,
        n_negative=n_neg,
        missing_period_count=inspect_view.missing_period_count,
        frequency_resolved=freq_ok,
        zero_share=zero_share,
        error_codes=list(inspect_view.error_codes),
        warning_codes=list(inspect_view.warning_codes),
        has_event_column=inspect_view.has_event,
        has_context_column=inspect_view.has_context,
        n_event_non_null=inspect_view.n_event_non_null,
        summary="; ".join(parts),
        limitations=limitations,
        confidence=confidence,
    )


def _inspect_summary(
    profile: SeriesProfile,
    error_codes: list[str],
    warning_codes: list[str],
) -> str:
    freq = profile.frequency.frequency or "unresolved"
    bits = [
        f"{profile.statistics.n_rows} row(s)",
        f"{profile.statistics.n_missing_values} missing value(s)",
        f"frequency={freq}",
        f"event_column={profile.has_event}",
        f"context_column={profile.has_context}",
    ]
    if error_codes:
        bits.append("errors=" + ",".join(error_codes))
    if warning_codes:
        bits.append("warnings=" + ",".join(warning_codes))
    return "; ".join(bits)


def _diagnostic_envelope(tool_name: str, result: DiagnosticResult) -> DataToolEnvelope:
    payload = result.model_dump(mode="json")
    payload["limitations"] = list(result.limitations) + [
        "Source values were copied for screening and were not modified."
    ]
    return DataToolEnvelope(tool_name=tool_name, ok=True, payload=payload)


def _frame_from_arrays(
    timestamps: pd.Series | pd.DatetimeIndex | None,
    values: pd.Series | np.ndarray | None,
) -> pd.DataFrame:
    y = np.asarray(values, dtype=float).copy()
    ts = pd.Series(timestamps).copy()
    return pd.DataFrame({TIMESTAMP_COL: ts, VALUE_COL: y})
