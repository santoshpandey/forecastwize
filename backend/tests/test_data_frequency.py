from __future__ import annotations

from datetime import UTC, datetime

import pandas as pd
from app.data.frequency import infer_frequency
from app.data.profiler import detect_missing_periods
from app.data.validator import inspect_csv


def test_infer_daily_frequency() -> None:
    stamps = pd.to_datetime(["2020-01-01", "2020-01-02", "2020-01-03", "2020-01-04"], utc=True)
    result = infer_frequency(stamps)
    assert result.frequency == "D"
    assert result.method == "pandas_infer_freq"
    assert result.n_unique_timestamps == 4


def test_gapped_daily_series_infers_daily() -> None:
    stamps = pd.to_datetime(["2020-01-01", "2020-01-02", "2020-01-04"], utc=True)
    result = infer_frequency(stamps)
    assert result.frequency == "D"
    assert result.method in {"pandas_infer_freq", "min_delta_multiples"}


def test_infer_hourly_frequency() -> None:
    stamps = pd.to_datetime(
        ["2020-01-01 00:00", "2020-01-01 01:00", "2020-01-01 02:00", "2020-01-01 03:00"],
        utc=True,
    )
    result = infer_frequency(stamps)
    assert result.frequency in {"h", "H"}
    assert result.frequency is not None


def test_unresolved_frequency_on_single_point() -> None:
    result = infer_frequency(pd.to_datetime(["2020-01-01"], utc=True))
    assert result.frequency is None
    assert result.method == "unresolved"


def test_median_delta_fallback_for_two_daily_points() -> None:
    stamps = pd.to_datetime(["2020-01-01", "2020-01-02"], utc=True)
    result = infer_frequency(stamps)
    assert result.frequency == "D"
    assert result.method == "median_delta"


def test_missing_periods_for_daily_gap() -> None:
    from io import StringIO

    text = "timestamp,value\n2020-01-01,1\n2020-01-02,2\n2020-01-04,4\n"
    inspection = inspect_csv(StringIO(text))
    assert inspection.is_valid()
    assert inspection.profile is not None
    assert inspection.profile.frequency.frequency == "D"
    periods = inspection.profile.missing_periods
    assert len(periods) == 1
    assert periods[0].n_steps == 1
    assert periods[0].start == datetime(2020, 1, 3, tzinfo=UTC)


def test_detect_missing_periods_no_freq_returns_empty() -> None:
    from app.data.schemas import FrequencyInference

    stamps = pd.to_datetime(["2020-01-01", "2020-01-04"], utc=True)
    unresolved = FrequencyInference(
        frequency=None,
        method="unresolved",
        median_delta_seconds=None,
        n_unique_timestamps=2,
        confidence="low",
        notes="test",
    )
    assert detect_missing_periods(pd.Series(stamps), unresolved, series_id=None) == []
