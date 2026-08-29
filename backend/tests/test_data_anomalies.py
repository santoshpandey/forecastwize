from __future__ import annotations

import inspect

import numpy as np
import pandas as pd
from app.data.anomalies import diagnose_outliers, diagnose_rolling_anomalies


def test_outlier_spike_is_flagged_and_input_unchanged() -> None:
    rng = np.random.default_rng(0)
    values = rng.normal(0.0, 1.0, 40)
    values[10] = 25.0
    original = values.copy()
    result = diagnose_outliers(values)
    np.testing.assert_array_equal(values, original)
    assert result.detected is True
    assert result.method == "modified_z_mad"
    assert 10 in result.evidence.indices
    assert result.evidence.n_flagged >= 1
    assert result.parameters
    assert result.limitations
    assert result.confidence in {"low", "medium", "high"}
    assert result.strength in {"none", "weak", "moderate", "strong"}


def test_outliers_insufficient_and_constant_series() -> None:
    short = diagnose_outliers(np.array([1.0, 2.0, 3.0]))
    assert short.detected is False
    assert "Insufficient" in short.evidence.summary or any(
        "at least" in item.lower() for item in short.limitations
    )
    constant = diagnose_outliers(np.ones(20))
    assert constant.detected is False
    assert any("MAD is 0" in item for item in constant.limitations)


def test_outliers_all_nan() -> None:
    result = diagnose_outliers(np.array([np.nan, np.nan, np.nan]))
    assert result.detected is False
    assert result.evidence.n_points_used == 0


def test_outliers_map_indices_through_nans() -> None:
    values = np.array([0.0, np.nan, 0.1, 0.0, 0.05, 0.0, 0.02, 0.0, 30.0, 0.01])
    result = diagnose_outliers(values)
    assert result.detected is True
    assert 8 in result.evidence.indices


def test_rolling_spike_causal_window() -> None:
    rng = np.random.default_rng(1)
    values = rng.normal(0.0, 1.0, 30)
    values[20] = 22.0
    original = values.copy()
    result = diagnose_rolling_anomalies(values, window=7)
    np.testing.assert_array_equal(values, original)
    assert result.detected is True
    assert result.method == "causal_rolling_mad"
    assert 20 in result.evidence.indices
    assert all(i >= 7 for i in result.evidence.indices)


def test_rolling_rejects_tiny_window_and_short_series() -> None:
    tiny = diagnose_rolling_anomalies(np.arange(20, dtype=float), window=3)
    assert tiny.detected is False
    short = diagnose_rolling_anomalies(np.arange(5, dtype=float), window=7)
    assert short.detected is False


def test_rolling_does_not_use_future_by_centering() -> None:
    source = inspect.getsource(diagnose_rolling_anomalies)
    assert "center=True" not in source


def test_anomaly_modules_have_no_llm() -> None:
    from app.data import anomalies

    text = inspect.getsource(anomalies).lower()
    assert "openai" not in text
    assert "fastapi" not in text
    assert "langgraph" not in text


def test_outliers_with_timestamps() -> None:
    values = np.concatenate([np.zeros(15), np.array([40.0]), np.zeros(14)])
    # add jitter so MAD is not zero
    rng = np.random.default_rng(2)
    values = values + rng.normal(0, 0.1, values.size)
    values[15] = 40.0
    stamps = pd.date_range("2020-01-01", periods=values.size, freq="D", tz="UTC")
    result = diagnose_outliers(values, stamps)
    assert result.detected is True
    assert result.evidence.timestamps
