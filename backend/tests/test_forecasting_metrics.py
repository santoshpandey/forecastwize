from __future__ import annotations

import numpy as np
import pytest
from app.forecasting.intervals import (
    IntervalOrderError,
    assert_interval_order,
    coverage_to_alpha,
    symmetric_intervals,
)
from app.forecasting.metrics import (
    interval_coverage,
    interval_score,
    interval_width,
    mae,
    mase,
    rmse,
    smape,
    wis,
    wmape,
)


def test_mae_rmse_basic_and_empty() -> None:
    assert mae([1.0, 2.0], [1.0, 4.0]) == pytest.approx(1.0)
    assert np.isnan(mae([], []))
    assert np.isnan(rmse([], []))


def test_rmse_known_value() -> None:
    assert rmse([0.0, 0.0], [3.0, 4.0]) == pytest.approx(np.sqrt((9.0 + 16.0) / 2.0))


def test_smape_zero_actuals() -> None:
    assert smape([0.0], [0.0]) == pytest.approx(0.0)
    assert smape([0.0], [1.0]) == pytest.approx(200.0)
    assert smape([1.0, 0.0], [1.0, 0.0]) == pytest.approx(0.0)


def test_smape_negatives() -> None:
    # | -2 - 0 | / (|-2|+|0|) * 200 = 200
    assert smape([-2.0], [0.0]) == pytest.approx(200.0)


def test_wmape_zero_denominator_is_nan() -> None:
    assert np.isnan(wmape([0.0, 0.0], [1.0, 2.0]))
    assert wmape([2.0, 2.0], [1.0, 3.0]) == pytest.approx(50.0)


def test_mase_naive_and_constant_insample() -> None:
    actual = np.array([2.0, 4.0])
    pred = np.array([2.0, 4.0])
    insample = np.array([1.0, 2.0, 3.0])
    # scale = mean(|2-1|, |3-2|) = 1, mae=0 -> 0
    assert mase(actual, pred, insample, seasonality_period=1) == pytest.approx(0.0)
    assert np.isnan(mase([1.0], [1.0], [5.0, 5.0, 5.0], seasonality_period=1))
    assert np.isnan(mase([1.0], [2.0], [1.0], seasonality_period=1))


def test_mase_seasonal_scale_zero_is_nan() -> None:
    insample = np.array([1.0, 2.0, 1.0, 2.0, 1.0, 2.0])
    assert np.isnan(mase([1.0], [2.0], insample, seasonality_period=2))


def test_mase_invalid_period() -> None:
    with pytest.raises(ValueError, match="seasonality_period"):
        mase([1.0], [1.0], [1.0, 2.0], seasonality_period=0)


def test_nan_handling_pairwise() -> None:
    assert mae([1.0, np.nan], [1.0, 9.0]) == pytest.approx(0.0)
    assert np.isnan(mae([np.nan], [np.nan]))
    assert mae([1.0, 3.0], [1.0, np.nan]) == pytest.approx(0.0)


def test_shape_mismatch_raises() -> None:
    with pytest.raises(ValueError, match="shape"):
        mae([1.0], [1.0, 2.0])


def test_interval_metrics_and_ordering() -> None:
    actual = np.array([0.0, 0.5, 2.0])
    lower = np.array([-1.0, 0.0, 1.5])
    upper = np.array([1.0, 1.0, 2.5])
    assert interval_coverage(actual, lower, upper) == pytest.approx(1.0)
    assert interval_width(lower, upper) == pytest.approx(np.mean([2.0, 1.0, 1.0]))
    assert interval_score(actual, lower, upper, coverage=0.5) > 0
    with pytest.raises(IntervalOrderError):
        interval_coverage([0.0], [1.0], [0.0])


def test_interval_metrics_empty_and_nan() -> None:
    assert np.isnan(interval_coverage([], [], []))
    assert np.isnan(interval_width([np.nan], [np.nan]))
    assert np.isnan(interval_score([np.nan], [0.0], [1.0], coverage=0.9))


def test_wis_perfect_and_miss() -> None:
    # y=m=0, interval [-1,1], coverage 0.5 => α=0.5, IS=2
    # WIS = 1/1.5 * (0 + 0.25*2) = 1/3
    assert wis([0.0], [0.0], [-1.0], [1.0], coverage=0.5) == pytest.approx(1.0 / 3.0)
    missed = wis([2.0], [0.0], [-1.0], [1.0], coverage=0.5)
    assert missed > wis([0.0], [0.0], [-1.0], [1.0], coverage=0.5)


def test_wis_nan_and_inverted() -> None:
    assert np.isnan(wis([np.nan], [0.0], [-1.0], [1.0], coverage=0.9))
    with pytest.raises(IntervalOrderError):
        wis([0.0], [0.0], [1.0], [-1.0], coverage=0.9)


def test_coverage_to_alpha_and_symmetric() -> None:
    assert coverage_to_alpha(0.95) == pytest.approx(0.05)
    with pytest.raises(Exception):
        coverage_to_alpha(1.0)
    yhat = np.array([0.0, 1.0])
    original = yhat.copy()
    lower, upper = symmetric_intervals(yhat, 2.0)
    np.testing.assert_array_equal(yhat, original)
    np.testing.assert_array_equal(lower, np.array([-2.0, -1.0]))
    np.testing.assert_array_equal(upper, np.array([2.0, 3.0]))
    assert_interval_order(lower, upper)


def test_negative_values_mae() -> None:
    assert mae([-1.0, -3.0], [0.0, -3.0]) == pytest.approx(0.5)
