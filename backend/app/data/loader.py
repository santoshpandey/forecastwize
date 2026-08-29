from __future__ import annotations

from pathlib import Path
from typing import IO

import pandas as pd

from app.data.schemas import SeriesValidationError, ValidationIssue


def load_csv(source: str | Path | IO[str] | IO[bytes]) -> pd.DataFrame:
    """Parse a CSV into a new DataFrame.

    The file on disk is never written. The returned frame is a copy of the parse
    result so callers can inspect without sharing a mutable parse buffer.
    Timestamps and values are left as raw CSV dtypes until validation.
    """
    try:
        frame = pd.read_csv(source, encoding="utf-8-sig")
    except UnicodeDecodeError as exc:
        raise SeriesValidationError(
            [
                ValidationIssue(
                    severity="error",
                    code="csv_parse_failed",
                    message="CSV is not valid UTF-8 (utf-8-sig).",
                )
            ]
        ) from exc
    except (OSError, pd.errors.ParserError, pd.errors.EmptyDataError, ValueError) as exc:
        raise SeriesValidationError(
            [
                ValidationIssue(
                    severity="error",
                    code="csv_parse_failed",
                    message=f"Could not parse CSV: {exc}",
                )
            ]
        ) from exc

    columns = [str(col).strip() for col in frame.columns]
    if len(columns) != len(set(columns)):
        raise SeriesValidationError(
            [
                ValidationIssue(
                    severity="error",
                    code="duplicate_column_names",
                    message="CSV header contains duplicate column names after trimming whitespace.",
                )
            ]
        )
    renamed = frame.copy()
    renamed.columns = columns
    return renamed.copy()


def dataframe_snapshot(frame: pd.DataFrame) -> pd.DataFrame:
    """Copy used so inspection never aliases the caller's object."""
    return frame.copy(deep=True)
