from __future__ import annotations

from io import StringIO

import pandas as pd
from app.data.loader import load_csv
from app.data.validator import inspect_csv, inspect_frame


def test_statistics_on_simple_series() -> None:
    text = "timestamp,value\n2020-01-01,1\n2020-01-02,2\n2020-01-03,3\n"
    inspection = inspect_csv(StringIO(text))
    assert inspection.profile is not None
    stats = inspection.profile.statistics
    assert stats.n_rows == 3
    assert stats.n_unique_timestamps == 3
    assert stats.n_missing_values == 0
    assert stats.n_duplicate_timestamps == 0
    assert stats.value_min == 1.0
    assert stats.value_max == 3.0
    assert stats.value_mean == 2.0
    assert stats.value_median == 2.0
    assert stats.value_std_sample is not None
    assert stats.n_zeros == 0
    assert stats.n_negative == 0


def test_missing_values_recorded_not_filled() -> None:
    text = "timestamp,value\n2020-01-01,1\n2020-01-02,\n2020-01-03,3\n"
    inspection = inspect_csv(StringIO(text))
    assert inspection.is_valid()
    assert inspection.profile is not None
    assert inspection.profile.statistics.n_missing_values == 1
    assert int(inspection.derived["value"].isna().sum()) == 1
    assert any(item.code == "missing_value" for item in inspection.issues)
    assert bool(pd.isna(inspection.original.loc[1, "value"]))


def test_zeros_and_negatives_counted() -> None:
    text = "timestamp,value\n2020-01-01,0\n2020-01-02,-4\n2020-01-03,5\n"
    inspection = inspect_csv(StringIO(text))
    assert inspection.profile is not None
    assert inspection.profile.statistics.n_zeros == 1
    assert inspection.profile.statistics.n_negative == 1


def test_inspect_frame_uses_copy_of_loaded_csv() -> None:
    frame = load_csv(StringIO("timestamp,value\n2020-01-01,1\n2020-01-02,2\n2020-01-03,3\n"))
    inspection = inspect_frame(frame)
    frame.loc[0, "value"] = 999
    assert inspection.original.loc[0, "value"] != 999
