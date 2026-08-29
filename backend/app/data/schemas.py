from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_serializer

TIMESTAMP_COL = "timestamp"
VALUE_COL = "value"
SERIES_ID_COL = "series_id"
CONTEXT_COL = "context"
EVENT_COL = "event"

REQUIRED_COLUMNS = (TIMESTAMP_COL, VALUE_COL)
OPTIONAL_KNOWN_COLUMNS = (SERIES_ID_COL, CONTEXT_COL, EVENT_COL)

IssueSeverity = Literal["error", "warning"]
FrequencyMethod = Literal["pandas_infer_freq", "median_delta", "min_delta_multiples", "unresolved"]


def _to_utc_iso(value: datetime) -> str:
    aware = value if value.tzinfo is not None else value.replace(tzinfo=UTC)
    return aware.astimezone(UTC).isoformat().replace("+00:00", "Z")


class ValidationIssue(BaseModel):
    """One validation or diagnostic finding. Does not mutate source data."""

    model_config = ConfigDict(extra="forbid")

    severity: IssueSeverity
    code: str
    message: str
    series_id: str | None = None
    timestamp: datetime | None = None
    row_number: int | None = Field(
        default=None,
        description="1-based data row number (header is row 0 from the parser's perspective).",
    )

    @field_serializer("timestamp")
    def serialize_timestamp(self, value: datetime | None) -> str | None:
        if value is None:
            return None
        return _to_utc_iso(value)


class FrequencyInference(BaseModel):
    """Explicit frequency result. Callers must not assume a freq when `frequency` is None."""

    model_config = ConfigDict(extra="forbid")

    frequency: str | None = Field(
        default=None,
        description="Pandas offset alias (e.g. D, h, W-SUN, MS) or null if unresolved.",
    )
    method: FrequencyMethod
    median_delta_seconds: float | None = None
    n_unique_timestamps: int
    confidence: Literal["high", "medium", "low"]
    notes: str


class MissingPeriod(BaseModel):
    """Consecutive missing steps on an inferred regular index."""

    model_config = ConfigDict(extra="forbid")

    start: datetime
    end: datetime
    n_steps: int
    series_id: str | None = None

    @field_serializer("start", "end")
    def serialize_bound(self, value: datetime) -> str:
        return _to_utc_iso(value)


class SeriesStatistics(BaseModel):
    """Descriptive stats on non-null values. NaNs are counted, not filled."""

    model_config = ConfigDict(extra="forbid")

    n_rows: int
    n_unique_timestamps: int
    n_missing_values: int
    n_duplicate_timestamps: int
    n_zeros: int
    n_negative: int
    start: datetime | None = None
    end: datetime | None = None
    value_min: float | None = None
    value_max: float | None = None
    value_mean: float | None = None
    value_median: float | None = None
    value_std_sample: float | None = Field(
        default=None,
        description="Sample standard deviation (ddof=1). Null if fewer than two non-null values.",
    )

    @field_serializer("start", "end")
    def serialize_range(self, value: datetime | None) -> str | None:
        if value is None:
            return None
        return _to_utc_iso(value)


class SeriesProfile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    statistics: SeriesStatistics
    frequency: FrequencyInference
    missing_periods: list[MissingPeriod]
    has_series_id: bool
    has_context: bool
    has_event: bool
    extra_columns: list[str]
    n_event_non_null: int = 0
    n_context_non_null: int = 0
    naive_timestamps_treated_as_utc: bool


class SeriesValidationError(ValueError):
    """Raised when error-severity issues prevent a reliable canonical series."""

    def __init__(self, issues: list[ValidationIssue]) -> None:
        self.issues = issues
        summary = "; ".join(f"{item.code}: {item.message}" for item in issues)
        super().__init__(summary)


DiagnosticStrength = Literal["none", "weak", "moderate", "strong"]
DiagnosticConfidence = Literal["low", "medium", "high"]


class DiagnosticParam(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    value: str | int | float | bool | None = None


class DiagnosticEvidence(BaseModel):
    model_config = ConfigDict(extra="forbid")

    summary: str
    n_points_used: int
    n_flagged: int = 0
    statistic: float | None = None
    statistic_name: str | None = None
    timestamps: list[datetime] = Field(default_factory=list)
    indices: list[int] = Field(default_factory=list)
    scores: list[float] = Field(default_factory=list)

    @field_serializer("timestamps")
    def serialize_timestamps(self, value: list[datetime]) -> list[str]:
        return [_to_utc_iso(item) for item in value]


class DiagnosticResult(BaseModel):
    """Conservative finding. `detected` is True only for a positive flag,
    never for insufficient data.
    """

    model_config = ConfigDict(extra="forbid")

    name: str
    detected: bool
    method: str
    parameters: list[DiagnosticParam]
    evidence: DiagnosticEvidence
    strength: DiagnosticStrength
    confidence: DiagnosticConfidence
    limitations: list[str]
