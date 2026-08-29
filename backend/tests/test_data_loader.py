from __future__ import annotations

import inspect
from io import StringIO
from pathlib import Path

import pandas as pd
import pytest
from app.data.loader import load_csv
from app.data.schemas import SeriesValidationError
from app.data.validator import inspect_csv, inspect_frame, validate_csv


def _csv(text: str) -> StringIO:
    return StringIO(text)


def test_load_csv_strips_header_whitespace(tmp_path: Path) -> None:
    path = tmp_path / "series.csv"
    path.write_text(" timestamp , value \n2020-01-01,1.0\n", encoding="utf-8")
    frame = load_csv(path)
    assert list(frame.columns) == ["timestamp", "value"]
    assert frame.loc[0, "value"] == pytest.approx(1.0)


def test_inspect_does_not_mutate_caller_frame() -> None:
    frame = load_csv(_csv("timestamp,value\n2020-01-02,2\n2020-01-01,1\n"))
    snapshot = frame.copy(deep=True)
    inspect_frame(frame)
    pd.testing.assert_frame_equal(frame, snapshot)


def test_derived_is_sorted_chronologically_original_order_preserved() -> None:
    original_csv = "timestamp,value\n2020-01-03,3\n2020-01-01,1\n2020-01-02,2\n"
    inspection = inspect_csv(_csv(original_csv))
    assert inspection.is_valid()
    assert inspection.profile is not None
    derived_dates = list(inspection.derived["timestamp"].dt.strftime("%Y-%m-%d"))
    assert derived_dates == ["2020-01-01", "2020-01-02", "2020-01-03"]
    original_dates = list(inspection.original["timestamp"].astype(str))
    assert original_dates == ["2020-01-03", "2020-01-01", "2020-01-02"]


def test_optional_series_id_context_event_and_extra_columns_preserved() -> None:
    text = (
        "timestamp,value,series_id,context,event,store\n"
        "2020-01-01,10,a,promo,holiday,west\n"
        "2020-01-02,11,a,promo,,west\n"
        "2020-01-03,12,a,,,west\n"
    )
    inspection = inspect_csv(_csv(text))
    assert inspection.is_valid()
    assert inspection.profile is not None
    assert inspection.profile.has_series_id is True
    assert inspection.profile.has_context is True
    assert inspection.profile.has_event is True
    assert inspection.profile.extra_columns == ["store"]
    assert inspection.profile.n_context_non_null == 2
    assert inspection.profile.n_event_non_null == 1
    assert "store" in inspection.derived.columns


def test_missing_required_columns() -> None:
    inspection = inspect_csv(_csv("date,amount\n2020-01-01,1\n"))
    assert not inspection.is_valid()
    codes = [item.code for item in inspection.error_issues()]
    assert "missing_required_columns" in codes


def test_invalid_timestamp_is_error() -> None:
    inspection = inspect_csv(_csv("timestamp,value\nnot-a-date,1\n2020-01-02,2\n"))
    assert not inspection.is_valid()
    assert any(item.code == "invalid_timestamp" for item in inspection.error_issues())


def test_invalid_value_is_error() -> None:
    inspection = inspect_csv(_csv("timestamp,value\n2020-01-01,abc\n"))
    assert not inspection.is_valid()
    assert any(item.code == "invalid_value" for item in inspection.error_issues())


def test_duplicate_timestamps_are_errors_and_not_dropped() -> None:
    text = "timestamp,value\n2020-01-01,1\n2020-01-01,9\n2020-01-02,2\n"
    inspection = inspect_csv(_csv(text))
    assert not inspection.is_valid()
    assert any(item.code == "duplicate_timestamps" for item in inspection.error_issues())
    assert len(inspection.derived) == 3


def test_validate_csv_raises_with_clear_message() -> None:
    with pytest.raises(SeriesValidationError, match="missing_required_columns"):
        validate_csv(_csv("x,y\n1,2\n"))


def test_data_modules_do_not_import_fastapi_or_llm() -> None:
    from app.data import frequency, loader, profiler, validator

    for module in (frequency, loader, profiler, validator):
        source = inspect.getsource(module)
        lowered = source.lower()
        assert "fastapi" not in lowered
        assert "openai" not in lowered
        assert "langgraph" not in lowered
        assert "anthropic" not in lowered
