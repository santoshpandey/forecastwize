from __future__ import annotations

import inspect
from datetime import UTC, datetime

import numpy as np
import pytest
from app.forecasting.base import ForecastInterfaceError
from app.tools.backtest_tools import BacktestToolSpec, run_backtest_tool
from app.tools.forecasting_tools import (
    EVALUATE_CANDIDATES,
    LIST_SUPPORTED_MODELS,
    EvaluateCandidatesSpec,
    compact_comparison,
    reject_unknown_forecast_tool,
    reject_unsupported_model_ids,
    run_evaluate_candidates_tool,
    run_named_forecast_tool,
)
from pydantic import ValidationError

from tests.ts_fixtures import daily_index


def test_forecasting_tools_source_has_no_fastapi_llm_or_selection() -> None:
    from app.tools import forecasting_tools

    text = inspect.getsource(forecasting_tools).lower()
    assert "import fastapi" not in text
    assert "import openai" not in text
    assert "langgraph" not in text
    assert "yhat =" not in text


def test_unknown_forecast_tool_is_rejected() -> None:
    with pytest.raises(ForecastInterfaceError, match="Unknown tool"):
        reject_unknown_forecast_tool("forecast_fit")
    reject_unknown_forecast_tool(EVALUATE_CANDIDATES)
    reject_unknown_forecast_tool(LIST_SUPPORTED_MODELS)


def test_unsupported_model_is_rejected() -> None:
    with pytest.raises(ForecastInterfaceError, match="Unsupported model_id"):
        reject_unsupported_model_ids(("prophet",))
    stamps = daily_index(20)
    values = np.arange(20, dtype=float)
    env = run_evaluate_candidates_tool(
        stamps,
        values,
        EvaluateCandidatesSpec(
            model_ids=("prophet",),
            frequency="D",
            horizon=2,
            min_train_size=8,
        ),
    )
    assert env.ok is False
    assert "Unsupported" in (env.error_message or "")


def test_evaluate_candidates_defaults_to_shared_origin_planning() -> None:
    spec = EvaluateCandidatesSpec(
        model_ids=("naive",),
        frequency="D",
        horizon=2,
        min_train_size=8,
    )
    assert spec.origin_planning == "shared"


def test_evaluate_candidates_matches_backtest_ranking() -> None:
    stamps = daily_index(28)
    values = np.linspace(1.0, 4.0, 28)
    spec = EvaluateCandidatesSpec(
        model_ids=("naive",),
        frequency="D",
        horizon=3,
        min_train_size=8,
        step=5,
        seed=1,
        origin_planning="shared",
    )
    env = run_named_forecast_tool(
        EVALUATE_CANDIDATES,
        stamps,
        values,
        spec,
        generated_at=datetime(2021, 1, 1, tzinfo=UTC),
    )
    assert env.ok is True
    assert env.payload["backtest_executed"] is True
    assert "yhat" not in env.payload
    comparison = run_backtest_tool(
        stamps,
        values,
        BacktestToolSpec(
            model_ids=("naive",),
            frequency="D",
            horizon=3,
            min_train_size=8,
            step=5,
            seed=1,
        ),
        generated_at=datetime(2021, 1, 1, tzinfo=UTC),
    )
    compact = compact_comparison(comparison, n_observations=28)
    assert env.payload["candidates"][0]["official_wis"] == compact.candidates[0].official_wis
    assert env.payload["candidates"][0]["rank"] == compact.candidates[0].rank
    assert env.payload["origin_planning"] == "shared"


def test_evaluate_candidates_model_specific_uses_official_wis() -> None:
    stamps = daily_index(40)
    values = np.linspace(1.0, 8.0, 40)
    spec = EvaluateCandidatesSpec(
        model_ids=("naive", "ets"),
        frequency="D",
        horizon=3,
        min_train_size=8,
        origin_planning="model_specific",
        target_folds=5,
        seed=1,
        seasonal_period=7,
        seasonality_period=7,
    )
    env = run_evaluate_candidates_tool(stamps, values, spec)
    assert env.ok is True
    assert env.payload["origin_planning"] == "model_specific"
    assert env.payload["selection_rule"] == "official_backtest_wis"
    rows = {item["model_id"]: item for item in env.payload["candidates"]}
    assert rows["ets"]["min_train_size"] == 16
    assert rows["ets"]["n_folds_failed"] == 0
    assert rows["ets"]["official_wis"] is not None
    assert rows["ets"]["eligible"] is True
    winner = min(
        (item for item in env.payload["candidates"] if item["rank"] is not None),
        key=lambda item: item["rank"],
    )
    assert winner["official_wis"] is not None
    assert winner["n_folds_failed"] == 0
    assert winner["wis_completed_only"] is not None


def test_list_supported_models() -> None:
    env = run_named_forecast_tool(LIST_SUPPORTED_MODELS)
    assert env.ok is True
    assert "naive" in env.payload["model_ids"]


def test_evaluate_spec_rejects_unknown_fields() -> None:
    with pytest.raises(ValidationError):
        EvaluateCandidatesSpec(
            model_ids=("naive",),
            frequency="D",
            horizon=2,
            min_train_size=8,
            extra=True,  # type: ignore[call-arg]
        )
