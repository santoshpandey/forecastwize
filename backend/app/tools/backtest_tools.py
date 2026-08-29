"""Deterministic backtest tool. Agents request this; they do not compute scores."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime

import numpy as np
import pandas as pd
from pydantic import BaseModel, ConfigDict, Field

from app.forecasting.backtesting import (
    BacktestComparison,
    BacktestSpec,
    WindowType,
    run_rolling_origin_backtest,
)
from app.forecasting.base import ForecastInterfaceError, ForecastModel
from app.services.forecast_service import BASELINE_MODEL_IDS, create_baseline_model

TOOL_NAME = "backtest"


class BacktestToolSpec(BaseModel):
    """Allowlisted arguments for the backtest tool. Unknown fields are rejected."""

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


def run_backtest_tool(
    timestamps: pd.Series | pd.DatetimeIndex,
    values: pd.Series | np.ndarray,
    spec: BacktestToolSpec,
    *,
    generated_at: datetime | None = None,
) -> BacktestComparison:
    """Run rolling-origin backtesting via the shared forecasting engine.

    Baseline callers and an agent graph must use this same numerical path
    (``run_rolling_origin_backtest``). This wrapper only constructs named
    baseline models. It does not call an LLM and does not emit yhat itself.
    """
    factories = _named_model_factories(spec.model_ids, spec.seasonal_period)
    engine_spec = BacktestSpec(
        frequency=spec.frequency,
        horizon=spec.horizon,
        min_train_size=spec.min_train_size,
        window_type=spec.window_type,
        rolling_window_size=spec.rolling_window_size,
        step=spec.step,
        coverage=spec.coverage,
        seed=spec.seed,
        seasonality_period=spec.seasonality_period,
    )
    return run_rolling_origin_backtest(
        timestamps,
        values,
        factories,
        engine_spec,
        generated_at=generated_at,
    )


def reject_unknown_tool(name: str) -> None:
    """Agents may only request the registered backtest tool name."""
    if name != TOOL_NAME:
        msg = f"Unknown tool {name!r}. Approved backtest tool is {TOOL_NAME!r}."
        raise ForecastInterfaceError(msg)


def run_named_tool(
    name: str,
    timestamps: pd.Series | pd.DatetimeIndex,
    values: pd.Series | np.ndarray,
    spec: BacktestToolSpec,
    *,
    generated_at: datetime | None = None,
) -> BacktestComparison:
    reject_unknown_tool(name)
    return run_backtest_tool(timestamps, values, spec, generated_at=generated_at)


def _named_model_factories(
    model_ids: tuple[str, ...],
    seasonal_period: int | None,
) -> list[tuple[str, Callable[[], ForecastModel]]]:
    allowed = set(BASELINE_MODEL_IDS)
    seen: set[str] = set()
    factories: list[tuple[str, Callable[[], ForecastModel]]] = []
    for raw in model_ids:
        key = raw.strip().lower()
        if key not in allowed:
            msg = (
                f"Unknown model_id={raw!r}. Backtest tool allowlist: "
                f"{', '.join(BASELINE_MODEL_IDS)}."
            )
            raise ForecastInterfaceError(msg)
        if key in seen:
            msg = f"duplicate model_id={raw!r}"
            raise ForecastInterfaceError(msg)
        seen.add(key)
        factories.append((key, _factory(key, seasonal_period)))
    return factories


def _factory(
    model_id: str,
    seasonal_period: int | None,
) -> Callable[[], ForecastModel]:
    def _make() -> ForecastModel:
        return create_baseline_model(model_id, seasonal_period=seasonal_period)

    return _make
