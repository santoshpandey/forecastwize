from __future__ import annotations

import inspect

import numpy as np
import pytest
from app.forecasting.base import ForecastInterfaceError
from app.tools.data_tools import (
    DATA_TOOL_NAMES,
    DIAGNOSE_OUTLIERS,
    DIAGNOSE_QUALITY,
    DIAGNOSE_TREND,
    INSPECT_SERIES,
    DataToolSpec,
    reject_unknown_data_tool,
    run_inspect_series_tool,
    run_named_data_tool,
)
from pydantic import ValidationError

from tests.ts_fixtures import daily_index


def test_data_tools_source_has_no_fastapi_llm_or_forecast_fit() -> None:
    from app.tools import data_tools

    text = inspect.getsource(data_tools).lower()
    assert "import fastapi" not in text
    assert "import openai" not in text
    assert "langgraph" not in text
    assert "run_baseline_forecast" not in text
    assert "yhat =" not in text


def test_unknown_data_tool_is_rejected() -> None:
    with pytest.raises(ForecastInterfaceError, match="Unknown tool"):
        reject_unknown_data_tool("forecast_fit")
    for name in DATA_TOOL_NAMES:
        reject_unknown_data_tool(name)


def test_inspect_and_quality_do_not_modify_input() -> None:
    stamps = daily_index(40)
    values = np.linspace(1.0, 5.0, 40)
    original = values.copy()
    spec = DataToolSpec(frequency="D")
    inspect_env = run_named_data_tool(INSPECT_SERIES, stamps, values, spec)
    quality_env = run_named_data_tool(DIAGNOSE_QUALITY, stamps, values, spec)
    np.testing.assert_array_equal(values, original)
    assert inspect_env.ok is True
    assert inspect_env.payload["is_valid"] is True
    assert inspect_env.payload["has_event"] is False
    assert quality_env.ok is True
    assert "yhat" not in quality_env.payload


def test_outlier_tool_matches_diagnostic_and_does_not_invent_events() -> None:
    rng = np.random.default_rng(0)
    values = rng.normal(0.0, 1.0, 40)
    values[10] = 25.0
    original = values.copy()
    stamps = daily_index(40)
    env = run_named_data_tool(DIAGNOSE_OUTLIERS, stamps, values, DataToolSpec())
    np.testing.assert_array_equal(values, original)
    assert env.ok is True
    assert env.payload["detected"] is True
    assert 10 in env.payload["evidence"]["indices"]
    assert (
        "event" not in env.payload["evidence"]["summary"].lower()
        or "invent" not in env.payload["evidence"]["summary"].lower()
    )


def test_trend_tool_on_linear_series() -> None:
    values = np.linspace(0.0, 10.0, 40)
    stamps = daily_index(40)
    env = run_named_data_tool(DIAGNOSE_TREND, stamps, values, DataToolSpec(frequency="D"))
    assert env.payload["detected"] is True
    assert env.payload["name"] == "trend"


def test_inspect_rejects_length_mismatch() -> None:
    env = run_inspect_series_tool(daily_index(3), np.arange(5, dtype=float))
    assert env.ok is False
    assert env.error_type == "InvalidInput"
    assert "length" in (env.error_message or "")


def test_data_tool_spec_rejects_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        DataToolSpec(frequency="D", extra=True)  # type: ignore[call-arg]
