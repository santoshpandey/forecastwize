from __future__ import annotations

import numpy as np
import pytest
from app.forecasting.base import ForecastInterfaceError
from app.forecasting.missing_policy import (
    LINEAR_INTERPOLATE_TRAIN,
    apply_linear_interpolate_train,
)

from tests.ts_fixtures import daily_index


def test_no_missing_returns_copy_and_no_record() -> None:
    stamps = daily_index(5)
    values = np.arange(5, dtype=float)
    filled, record = apply_linear_interpolate_train(stamps, values)
    np.testing.assert_array_equal(filled, values)
    assert record is None
    values[0] = 99.0
    assert filled[0] == 0.0


def test_middle_gap_interpolates_without_holdout() -> None:
    stamps = daily_index(6)
    train = np.array([1.0, np.nan, 3.0, 4.0], dtype=float)
    holdout = np.array([999.0, 999.0], dtype=float)
    filled, record = apply_linear_interpolate_train(stamps[:4], train)
    assert record is not None
    assert record.policy == LINEAR_INTERPOLATE_TRAIN
    assert record.n_missing_before == 1
    assert record.applied is True
    assert filled[1] == pytest.approx(2.0)
    assert 999.0 not in filled
    np.testing.assert_array_equal(holdout, np.array([999.0, 999.0]))


def test_all_nan_train_fails() -> None:
    stamps = daily_index(3)
    with pytest.raises(ForecastInterfaceError, match=LINEAR_INTERPOLATE_TRAIN):
        apply_linear_interpolate_train(stamps, np.array([np.nan, np.nan, np.nan]))


def test_does_not_mutate_caller_values() -> None:
    stamps = daily_index(3)
    values = np.array([1.0, np.nan, 3.0])
    snapshot = values.copy()
    apply_linear_interpolate_train(stamps, values)
    np.testing.assert_array_equal(values, snapshot)
