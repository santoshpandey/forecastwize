from __future__ import annotations

import inspect

import numpy as np
from app.data.seasonality import diagnose_seasonality, diagnose_trend, period_from_frequency


def test_strong_linear_trend_detected() -> None:
    values = np.linspace(0.0, 10.0, 40)
    original = values.copy()
    result = diagnose_trend(values)
    np.testing.assert_array_equal(values, original)
    assert result.detected is True
    assert result.name == "trend"
    assert result.evidence.statistic is not None
    assert abs(result.evidence.statistic) >= 0.6
    assert result.limitations


def test_flat_series_no_trend() -> None:
    rng = np.random.default_rng(3)
    values = rng.normal(5.0, 0.2, 40)
    result = diagnose_trend(values)
    assert result.detected is False
    assert result.strength in {"none", "weak"}


def test_trend_insufficient_points() -> None:
    result = diagnose_trend(np.array([1.0, 2.0, 3.0]))
    assert result.detected is False
    assert result.confidence == "low"


def test_weekly_seasonality_detected() -> None:
    t = np.arange(56, dtype=float)
    values = 10.0 + 4.0 * np.sin(2.0 * np.pi * t / 7.0)
    original = values.copy()
    result = diagnose_seasonality(values, period=7)
    np.testing.assert_array_equal(values, original)
    assert result.detected is True
    assert result.evidence.statistic is not None
    assert result.evidence.statistic >= 0.4


def test_seasonality_from_daily_frequency_alias() -> None:
    t = np.arange(56, dtype=float)
    values = 3.0 * np.sin(2.0 * np.pi * t / 7.0)
    result = diagnose_seasonality(values, frequency="D")
    assert result.detected is True


def test_seasonality_unresolved_period() -> None:
    values = np.sin(np.linspace(0, 12, 56))
    result = diagnose_seasonality(values)
    assert result.detected is False
    assert any("period" in item.lower() for item in result.limitations)


def test_seasonality_too_few_cycles() -> None:
    values = np.sin(2.0 * np.pi * np.arange(10) / 7.0)
    result = diagnose_seasonality(values, period=7)
    assert result.detected is False


def test_period_from_frequency() -> None:
    assert period_from_frequency("D") == 7
    assert period_from_frequency("h") == 24
    assert period_from_frequency("MS") == 12
    assert period_from_frequency("W-SUN") == 52
    assert period_from_frequency("weird") is None


def test_seasonality_module_has_no_llm() -> None:
    from app.data import seasonality

    text = inspect.getsource(seasonality).lower()
    assert "openai" not in text
    assert "fastapi" not in text
