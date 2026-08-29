from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import IO

import pandas as pd

from app.data.loader import dataframe_snapshot, load_csv
from app.data.profiler import build_profile
from app.data.schemas import (
    OPTIONAL_KNOWN_COLUMNS,
    REQUIRED_COLUMNS,
    SERIES_ID_COL,
    TIMESTAMP_COL,
    VALUE_COL,
    SeriesProfile,
    SeriesValidationError,
    ValidationIssue,
)

_MAX_ISSUE_EXAMPLES = 20


@dataclass
class SeriesInspection:
    """Inspection result. `original` is a snapshot of the caller's frame (unmutated)."""

    original: pd.DataFrame
    derived: pd.DataFrame
    issues: list[ValidationIssue] = field(default_factory=list)
    profile: SeriesProfile | None = None

    def error_issues(self) -> list[ValidationIssue]:
        return [item for item in self.issues if item.severity == "error"]

    def is_valid(self) -> bool:
        return len(self.error_issues()) == 0


def inspect_frame(frame: pd.DataFrame) -> SeriesInspection:
    """Validate and profile a table without mutating `frame`."""
    original = dataframe_snapshot(frame)
    issues: list[ValidationIssue] = []
    derived = original.copy()

    missing_required = [col for col in REQUIRED_COLUMNS if col not in derived.columns]
    if missing_required:
        found = ", ".join(derived.columns.astype(str)) or "(none)"
        issues.append(
            ValidationIssue(
                severity="error",
                code="missing_required_columns",
                message=(
                    "CSV must include columns "
                    f"{list(REQUIRED_COLUMNS)}; missing {missing_required}. Found: {found}."
                ),
            )
        )
        return SeriesInspection(original=original, derived=derived, issues=issues, profile=None)

    if derived.empty:
        issues.append(
            ValidationIssue(
                severity="error",
                code="empty_table",
                message="CSV has a header but no data rows.",
            )
        )
        return SeriesInspection(original=original, derived=derived, issues=issues, profile=None)

    derived, ts_issues, naive_to_utc = _parse_timestamps(derived)
    issues.extend(ts_issues)
    derived, value_issues = _parse_values(derived)
    issues.extend(value_issues)
    if not any(item.code == "invalid_timestamp" for item in issues):
        issues.extend(_duplicate_timestamp_issues(derived))

    if any(item.severity == "error" for item in issues):
        return SeriesInspection(original=original, derived=derived, issues=issues, profile=None)

    sort_cols = [TIMESTAMP_COL]
    if SERIES_ID_COL in derived.columns:
        sort_cols.append(SERIES_ID_COL)
    derived = derived.sort_values(sort_cols, kind="mergesort").reset_index(drop=True)

    extra = [
        str(col)
        for col in derived.columns
        if col not in REQUIRED_COLUMNS and col not in OPTIONAL_KNOWN_COLUMNS
    ]
    profile = build_profile(
        derived, extra_columns=extra, naive_timestamps_treated_as_utc=naive_to_utc
    )
    issues.extend(_frequency_issues(profile))
    return SeriesInspection(original=original, derived=derived, issues=issues, profile=profile)


def inspect_csv(source: str | Path | IO[str] | IO[bytes]) -> SeriesInspection:
    return inspect_frame(load_csv(source))


def validate_csv(source: str | Path | IO[str] | IO[bytes]) -> SeriesInspection:
    return validate_frame(load_csv(source))


def validate_frame(frame: pd.DataFrame) -> SeriesInspection:
    """Inspect and raise SeriesValidationError if any error-severity issues exist."""
    inspection = inspect_frame(frame)
    errors = inspection.error_issues()
    if errors:
        raise SeriesValidationError(errors)
    return inspection


def _parse_timestamps(
    derived: pd.DataFrame,
) -> tuple[pd.DataFrame, list[ValidationIssue], bool]:
    issues: list[ValidationIssue] = []
    raw = derived[TIMESTAMP_COL]
    parsed = pd.to_datetime(raw, utc=True, errors="coerce", format="mixed")
    naive_to_utc = True
    invalid_mask = parsed.isna() & raw.notna() & (raw.astype(str).str.strip() != "")
    empty_mask = raw.isna() | (raw.astype(str).str.strip() == "")
    bad = invalid_mask | empty_mask
    examples = 0
    for idx in derived.index[bad]:
        if examples >= _MAX_ISSUE_EXAMPLES:
            remaining = int(bad.sum()) - examples
            issues.append(
                ValidationIssue(
                    severity="error",
                    code="invalid_timestamp",
                    message=f"{remaining} additional invalid or missing timestamp(s) omitted.",
                )
            )
            break
        row_number = int(idx) + 1
        issues.append(
            ValidationIssue(
                severity="error",
                code="invalid_timestamp",
                message=f"Timestamp is missing or not parseable at data row {row_number}.",
                row_number=row_number,
            )
        )
        examples += 1
    out = derived.copy()
    out[TIMESTAMP_COL] = parsed
    return out, issues, naive_to_utc


def _parse_values(derived: pd.DataFrame) -> tuple[pd.DataFrame, list[ValidationIssue]]:
    issues: list[ValidationIssue] = []
    raw = derived[VALUE_COL]
    numeric = pd.to_numeric(raw, errors="coerce")
    originally_blank = raw.isna() | (raw.astype(str).str.strip() == "")
    invalid = numeric.isna() & ~originally_blank
    examples = 0
    for idx in derived.index[invalid]:
        if examples >= _MAX_ISSUE_EXAMPLES:
            remaining = int(invalid.sum()) - examples
            issues.append(
                ValidationIssue(
                    severity="error",
                    code="invalid_value",
                    message=f"{remaining} additional non-numeric value(s) omitted.",
                )
            )
            break
        row_number = int(idx) + 1
        issues.append(
            ValidationIssue(
                severity="error",
                code="invalid_value",
                message=f"Value is not numeric at data row {row_number}.",
                row_number=row_number,
            )
        )
        examples += 1
    missing_count = int(originally_blank.sum())
    if missing_count:
        issues.append(
            ValidationIssue(
                severity="warning",
                code="missing_value",
                message=(
                    f"{missing_count} missing value(s) detected. "
                    "They are recorded, not filled or dropped."
                ),
            )
        )
    out = derived.copy()
    out[VALUE_COL] = numeric
    return out, issues


def _duplicate_timestamp_issues(derived: pd.DataFrame) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    subset = [TIMESTAMP_COL]
    if SERIES_ID_COL in derived.columns:
        subset = [SERIES_ID_COL, TIMESTAMP_COL]
    dup_mask = derived.duplicated(subset=subset, keep=False)
    if not bool(dup_mask.any()):
        return issues
    dup_rows = derived.loc[dup_mask]
    n_dup = int(dup_mask.sum())
    issues.append(
        ValidationIssue(
            severity="error",
            code="duplicate_timestamps",
            message=(
                f"{n_dup} rows share a timestamp"
                + (" within the same series_id" if SERIES_ID_COL in derived.columns else "")
                + ". Duplicate timestamps are not dropped."
            ),
        )
    )
    shown = 0
    for _, row in dup_rows.iterrows():
        if shown >= _MAX_ISSUE_EXAMPLES:
            break
        ts = row[TIMESTAMP_COL]
        series_id = str(row[SERIES_ID_COL]) if SERIES_ID_COL in derived.columns else None
        ts_dt = ts.to_pydatetime() if isinstance(ts, pd.Timestamp) else None
        issues.append(
            ValidationIssue(
                severity="error",
                code="duplicate_timestamp_example",
                message="Duplicate timestamp.",
                series_id=series_id,
                timestamp=ts_dt,
            )
        )
        shown += 1
    return issues


def _frequency_issues(profile: SeriesProfile) -> list[ValidationIssue]:
    if profile.frequency.frequency is not None:
        return []
    return [
        ValidationIssue(
            severity="warning",
            code="frequency_unresolved",
            message=profile.frequency.notes,
        )
    ]
