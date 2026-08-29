from __future__ import annotations

import inspect

import numpy as np
import pandas as pd
from app.data.structural_breaks import diagnose_structural_breaks


def test_mean_shift_detected() -> None:
    values = np.concatenate([np.full(40, 0.0), np.full(40, 8.0)])
    original = values.copy()
    result = diagnose_structural_breaks(values)
    np.testing.assert_array_equal(values, original)
    assert result.detected is True
    assert result.method == "single_mean_shift_welch_scan"
    assert result.evidence.indices
    split = result.evidence.indices[0]
    assert 20 <= split <= 60
    assert result.limitations
    assert result.evidence.statistic is not None
    assert abs(result.evidence.statistic) >= 4.0


def test_no_break_on_stable_noise() -> None:
    rng = np.random.default_rng(4)
    values = rng.normal(0.0, 1.0, 80)
    result = diagnose_structural_breaks(values)
    assert result.detected is False


def test_break_insufficient_length() -> None:
    result = diagnose_structural_breaks(np.arange(10, dtype=float))
    assert result.detected is False
    assert result.confidence == "low"


def test_break_with_timestamps() -> None:
    values = np.concatenate([np.full(30, 1.0), np.full(30, 9.0)])
    stamps = pd.date_range("2020-01-01", periods=60, freq="D", tz="UTC")
    result = diagnose_structural_breaks(values, stamps)
    assert result.detected is True
    assert result.evidence.timestamps


def test_structural_module_has_no_llm() -> None:
    from app.data import structural_breaks

    text = inspect.getsource(structural_breaks).lower()
    assert "openai" not in text
    assert "fastapi" not in text
    assert "langgraph" not in text
