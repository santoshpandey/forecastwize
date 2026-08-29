"""Series CSV load, validation, frequency, profiling, and diagnostics. No FastAPI or LLM."""

from app.data.anomalies import diagnose_outliers, diagnose_rolling_anomalies
from app.data.frequency import infer_frequency
from app.data.loader import load_csv
from app.data.profiler import build_profile, compute_statistics, detect_missing_periods
from app.data.schemas import (
    DiagnosticResult,
    FrequencyInference,
    MissingPeriod,
    SeriesProfile,
    SeriesStatistics,
    SeriesValidationError,
    ValidationIssue,
)
from app.data.seasonality import diagnose_seasonality, diagnose_trend
from app.data.structural_breaks import diagnose_structural_breaks
from app.data.validator import (
    SeriesInspection,
    inspect_csv,
    inspect_frame,
    validate_csv,
    validate_frame,
)

__all__ = [
    "DiagnosticResult",
    "FrequencyInference",
    "MissingPeriod",
    "SeriesInspection",
    "SeriesProfile",
    "SeriesStatistics",
    "SeriesValidationError",
    "ValidationIssue",
    "build_profile",
    "compute_statistics",
    "detect_missing_periods",
    "diagnose_outliers",
    "diagnose_rolling_anomalies",
    "diagnose_seasonality",
    "diagnose_structural_breaks",
    "diagnose_trend",
    "infer_frequency",
    "inspect_csv",
    "inspect_frame",
    "load_csv",
    "validate_csv",
    "validate_frame",
]
