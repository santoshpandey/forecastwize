from __future__ import annotations

import inspect
from datetime import UTC, datetime

import numpy as np
import pytest
from app.forecasting.backtesting import BacktestSpec, run_rolling_origin_backtest
from app.forecasting.base import ForecastInterfaceError
from app.forecasting.naive import NaiveModel
from app.tools.backtest_tools import (
    TOOL_NAME,
    BacktestToolSpec,
    reject_unknown_tool,
    run_backtest_tool,
    run_named_tool,
)
from pydantic import ValidationError

from tests.ts_fixtures import daily_index


def test_backtest_tools_source_has_no_fastapi_or_llm() -> None:
    from app.tools import backtest_tools

    text = inspect.getsource(backtest_tools).lower()
    assert "import fastapi" not in text
    assert "import openai" not in text
    assert "langgraph" not in text


def test_unknown_tool_name_is_rejected() -> None:
    with pytest.raises(ForecastInterfaceError, match="Unknown tool"):
        reject_unknown_tool("forecast_fit")
    reject_unknown_tool(TOOL_NAME)


def test_tool_rejects_unknown_and_duplicate_model_ids() -> None:
    stamps = daily_index(10)
    values = np.arange(10, dtype=float)
    with pytest.raises(ForecastInterfaceError, match="Unknown model_id"):
        run_backtest_tool(
            stamps,
            values,
            BacktestToolSpec(
                model_ids=("not_a_model",),
                frequency="D",
                horizon=2,
                min_train_size=5,
            ),
        )
    with pytest.raises(ForecastInterfaceError, match="duplicate"):
        run_backtest_tool(
            stamps,
            values,
            BacktestToolSpec(
                model_ids=("naive", "naive"),
                frequency="D",
                horizon=2,
                min_train_size=5,
            ),
        )
    with pytest.raises(ValidationError):
        BacktestToolSpec(
            model_ids=(),
            frequency="D",
            horizon=2,
            min_train_size=5,
        )
    with pytest.raises(ValidationError):
        BacktestToolSpec(
            model_ids=("naive",),
            frequency="D",
            horizon=2,
            min_train_size=5,
            extra_field=True,  # type: ignore[call-arg]
        )


def test_tool_and_engine_return_the_same_comparison() -> None:
    stamps = daily_index(10)
    values = np.arange(10, dtype=float)
    generated = datetime(2021, 3, 4, tzinfo=UTC)
    tool_spec = BacktestToolSpec(
        model_ids=("naive",),
        frequency="D",
        horizon=2,
        min_train_size=5,
        window_type="expanding",
        step=1,
        coverage=0.9,
        seed=3,
        seasonality_period=1,
    )
    via_tool = run_named_tool("backtest", stamps, values, tool_spec, generated_at=generated)
    via_engine = run_rolling_origin_backtest(
        stamps,
        values,
        [("naive", NaiveModel)],
        BacktestSpec(
            frequency="D",
            horizon=2,
            min_train_size=5,
            window_type="expanding",
            step=1,
            coverage=0.9,
            seed=3,
            seasonality_period=1,
        ),
        generated_at=generated,
    )
    assert via_tool.model_dump() == via_engine.model_dump()
    assert via_tool.results[0].model_id == "naive"
    assert via_tool.configuration["selection"] == "none_comparison_only"


def test_tool_compares_multiple_named_models() -> None:
    stamps = daily_index(16)
    t = np.arange(16, dtype=float)
    values = 2.0 + 0.1 * t + np.sin(2.0 * np.pi * t / 7.0)
    result = run_backtest_tool(
        stamps,
        values,
        BacktestToolSpec(
            model_ids=("naive", "seasonal_naive"),
            frequency="D",
            horizon=2,
            min_train_size=8,
            coverage=0.95,
            seed=1,
            seasonality_period=7,
        ),
        generated_at=datetime(2021, 1, 1, tzinfo=UTC),
    )
    assert result.model_ids == ["naive", "seasonal_naive"]
    assert len(result.results) == 2
    assert result.folds_planned
    assert result.results[0].folds[0].metadata is not None
    assert result.results[1].folds[0].metadata is not None
    for row in result.results:
        assert row.aggregate.n_folds_planned == len(result.folds_planned)
        assert row.aggregate.n_folds_failed == 0
        assert row.aggregate.wis is not None
