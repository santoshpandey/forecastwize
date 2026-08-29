"""Run an explicitly named baseline model. No agent selection. No HTTP. No LLM."""

from __future__ import annotations

from datetime import datetime

import numpy as np
import pandas as pd

from app.forecasting._support import as_utc_last, future_index
from app.forecasting.arima import ARIMAModel
from app.forecasting.base import (
    ForecastInterfaceError,
    ForecastModel,
    ForecastResult,
    assemble_forecast_result,
)
from app.forecasting.ets import ETSModel
from app.forecasting.naive import NaiveModel
from app.forecasting.seasonal_naive import SeasonalNaiveModel

BASELINE_MODEL_IDS = ("naive", "seasonal_naive", "ets", "arima")


def create_baseline_model(
    model_id: str,
    *,
    seasonal_period: int | None = None,
) -> ForecastModel:
    """Construct one baseline model. `model_id` is required; nothing is auto-selected."""
    key = model_id.strip().lower()
    if key == "naive":
        return NaiveModel()
    if key == "seasonal_naive":
        return SeasonalNaiveModel(seasonal_period=seasonal_period)
    if key == "ets":
        return ETSModel(seasonal_period=seasonal_period)
    if key == "arima":
        return ARIMAModel(seasonal_period=seasonal_period)
    allowed = ", ".join(BASELINE_MODEL_IDS)
    msg = f"Unknown baseline model_id={model_id!r}. Pass one of: {allowed}."
    raise ForecastInterfaceError(msg)


def run_baseline_forecast(
    timestamps: pd.Series | pd.DatetimeIndex,
    values: pd.Series | np.ndarray,
    *,
    frequency: str,
    horizon: int,
    model_id: str,
    coverage: float = 0.95,
    seed: int | None = None,
    seasonal_period: int | None = None,
    generated_at: datetime | None = None,
) -> ForecastResult:
    """Fit the named baseline and return a ForecastResult.

    Does not compare models, does not call an LLM, and does not write evaluation
    scores. Callers must supply `model_id` explicitly.
    """
    model = create_baseline_model(model_id, seasonal_period=seasonal_period)
    model.fit(timestamps, values, frequency=frequency, seed=seed)
    yhat = model.predict(horizon=horizon)
    lower, upper = model.predict_interval(horizon=horizon, coverage=coverage)
    index = pd.DatetimeIndex(timestamps)
    future = future_index(as_utc_last(index), horizon=horizon, frequency=frequency)
    return assemble_forecast_result(
        timestamps=future,
        yhat=yhat,
        lower=lower,
        upper=upper,
        metadata=model.metadata(),
        forecast_horizon=horizon,
        interval_coverage_nominal=coverage,
        generated_at=generated_at,
    )
