"""Deterministic forecasting tools for agents. Evaluation is backtesting, not LLM scores.

Does not select a production model. Does not modify the caller's series. No FastAPI.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

import numpy as np
import pandas as pd
from pydantic import BaseModel, ConfigDict, Field

from app.forecasting.backtesting import BacktestComparison, WindowType
from app.forecasting.base import ForecastInterfaceError
from app.services.forecast_service import BASELINE_MODEL_IDS
from app.tools.backtest_tools import BacktestToolSpec, run_backtest_tool

EVALUATE_CANDIDATES = "evaluate_candidates"
LIST_SUPPORTED_MODELS = "list_supported_models"
FORECAST_TOOL_NAMES = (EVALUATE_CANDIDATES, LIST_SUPPORTED_MODELS)

JsonObject = dict[str, Any]


class CandidateEvalRow(BaseModel):
    """Compact backtest snapshot. Official WIS is from the forecasting engine."""

    model_config = ConfigDict(extra="forbid")

    model_id: str
    official_wis: float | None
    wis_completed_only: float | None
    n_folds_planned: int
    n_folds_completed: int
    n_folds_failed: int
    rank: int | None
    error_message: str | None = None


class EvaluateCandidatesSpec(BaseModel):
    """Allowlisted evaluation arguments. Unknown fields are rejected."""

    model_config = ConfigDict(extra="forbid")

    model_ids: tuple[str, ...] = Field(min_length=1)
    frequency: str
    horizon: int
    min_train_size: int
    window_type: WindowType = "expanding"
    rolling_window_size: int | None = None
    step: int = 1
    coverage: float = 0.95
    seed: int | None = None
    seasonal_period: int | None = None
    seasonality_period: int = 1


class ForecastToolEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tool_name: str
    ok: bool
    payload: JsonObject
    error_type: str | None = None
    error_message: str | None = None


class EvaluateCandidatesResult(BaseModel):
    """Compact backtest comparison. No production yhat. Official WIS from the engine."""

    model_config = ConfigDict(extra="forbid")

    frequency: str
    horizon: int
    min_train_size: int
    window_type: str
    n_observations: int
    model_ids: list[str]
    candidates: list[CandidateEvalRow]
    backtest_executed: bool = True


def reject_unknown_forecast_tool(name: str) -> None:
    if name not in FORECAST_TOOL_NAMES:
        allowed = ", ".join(FORECAST_TOOL_NAMES)
        msg = f"Unknown tool {name!r}. Approved forecasting tools: {allowed}."
        raise ForecastInterfaceError(msg)


def reject_unsupported_model_ids(model_ids: tuple[str, ...] | list[str]) -> None:
    allowed = set(BASELINE_MODEL_IDS)
    for raw in model_ids:
        key = str(raw).strip().lower()
        if key not in allowed:
            msg = f"Unsupported model_id={raw!r}. Allowlist: {', '.join(BASELINE_MODEL_IDS)}."
            raise ForecastInterfaceError(msg)


def run_named_forecast_tool(
    name: str,
    timestamps: pd.Series | pd.DatetimeIndex | None = None,
    values: pd.Series | np.ndarray | None = None,
    spec: EvaluateCandidatesSpec | None = None,
    *,
    generated_at: datetime | None = None,
) -> ForecastToolEnvelope:
    reject_unknown_forecast_tool(name)
    if name == LIST_SUPPORTED_MODELS:
        return run_list_supported_models_tool()
    if spec is None or timestamps is None or values is None:
        msg = "evaluate_candidates requires timestamps, values, and spec"
        raise ForecastInterfaceError(msg)
    return run_evaluate_candidates_tool(timestamps, values, spec, generated_at=generated_at)


def run_list_supported_models_tool() -> ForecastToolEnvelope:
    payload = {
        "model_ids": list(BASELINE_MODEL_IDS),
        "summary": "Supported baseline model_ids: " + ", ".join(BASELINE_MODEL_IDS),
    }
    return ForecastToolEnvelope(tool_name=LIST_SUPPORTED_MODELS, ok=True, payload=payload)


def run_evaluate_candidates_tool(
    timestamps: pd.Series | pd.DatetimeIndex,
    values: pd.Series | np.ndarray,
    spec: EvaluateCandidatesSpec,
    *,
    generated_at: datetime | None = None,
) -> ForecastToolEnvelope:
    """Run shared rolling-origin backtesting. Agents must not recompute WIS."""
    try:
        reject_unsupported_model_ids(spec.model_ids)
        y = np.asarray(values, dtype=float)
        if y.size == 0:
            msg = "values are empty"
            raise ForecastInterfaceError(msg)
        if not spec.frequency.strip():
            msg = "frequency must be a non-empty explicit alias"
            raise ForecastInterfaceError(msg)
        if spec.horizon < 1:
            msg = "horizon must be >= 1"
            raise ForecastInterfaceError(msg)
        backtest_spec = BacktestToolSpec(
            model_ids=spec.model_ids,
            frequency=spec.frequency,
            horizon=spec.horizon,
            min_train_size=spec.min_train_size,
            window_type=spec.window_type,
            rolling_window_size=spec.rolling_window_size,
            step=spec.step,
            coverage=spec.coverage,
            seed=spec.seed,
            seasonal_period=spec.seasonal_period,
            seasonality_period=spec.seasonality_period,
        )
        comparison = run_backtest_tool(timestamps, values, backtest_spec, generated_at=generated_at)
        result = compact_comparison(comparison, n_observations=int(y.size))
        return ForecastToolEnvelope(
            tool_name=EVALUATE_CANDIDATES,
            ok=True,
            payload=result.model_dump(mode="json"),
        )
    except ForecastInterfaceError as exc:
        return ForecastToolEnvelope(
            tool_name=EVALUATE_CANDIDATES,
            ok=False,
            payload={"backtest_executed": False, "summary": str(exc)},
            error_type="ForecastInterfaceError",
            error_message=str(exc),
        )


def compact_comparison(
    comparison: BacktestComparison,
    *,
    n_observations: int,
) -> EvaluateCandidatesResult:
    rank_by = {row.model_id: row for row in comparison.ranking}
    candidates: list[CandidateEvalRow] = []
    for result in comparison.results:
        ranked = rank_by.get(result.model_id)
        failed_fold = next(
            (fold for fold in result.folds if fold.status == "failed"),
            None,
        )
        candidates.append(
            CandidateEvalRow(
                model_id=result.model_id,
                official_wis=result.aggregate.wis,
                wis_completed_only=result.aggregate.wis_completed_only,
                n_folds_planned=result.aggregate.n_folds_planned,
                n_folds_completed=result.aggregate.n_folds_completed,
                n_folds_failed=result.aggregate.n_folds_failed,
                rank=ranked.rank if ranked is not None else None,
                error_message=None if failed_fold is None else failed_fold.error_message,
            )
        )
    return EvaluateCandidatesResult(
        frequency=comparison.spec.frequency,
        horizon=comparison.spec.horizon,
        min_train_size=comparison.spec.min_train_size,
        window_type=comparison.spec.window_type,
        n_observations=n_observations,
        model_ids=list(comparison.model_ids),
        candidates=candidates,
        backtest_executed=True,
    )
