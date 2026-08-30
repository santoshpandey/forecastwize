"""Additive Holt–Winters / ETS baseline. Deterministic MLE-style fit. No LLM."""

from __future__ import annotations

from typing import Any, Self

import numpy as np
import pandas as pd
from statsmodels.tsa.holtwinters import ExponentialSmoothing

from app.data.seasonality import period_from_frequency
from app.forecasting._support import (
    copy_training,
    random_walk_intervals,
    require_fitted,
    require_horizon,
    residual_sigma,
    training_range_of,
)
from app.forecasting.base import ForecastInterfaceError, ForecastModel, ModelMetadata


def ets_minimum_train_size(*, frequency: str, seasonal_period: int | None) -> int:
    """Same length rule as ``ETSModel.fit``.

    Seasonal ETS uses additive Holt–Winters with heuristic initialization.
    statsmodels requires ``10 + 2 * (m // 2)`` points for that initializer, which
    can exceed ``2 * m``. The returned value is the larger of those constraints.
    """
    period = seasonal_period if seasonal_period is not None else period_from_frequency(frequency)
    if period is not None and period >= 2:
        m = int(period)
        heuristic_n = 10 + 2 * (m // 2)
        return max(2 * m, heuristic_n)
    return 3


class ETSModel(ForecastModel):
    """Additive trend; additive seasonality only when a period >= 2 is known.

    Uses statsmodels ExponentialSmoothing with heuristic initialization and
    L-BFGS-B. Multiplicative seasonality is not used (zeros/negatives are valid
    in the rest of the stack). Prediction intervals fall back to residual √h
    if analytic intervals are unavailable.
    """

    def __init__(self, *, seasonal_period: int | None = None) -> None:
        self._period_arg = seasonal_period
        self._fitted = False
        self._y: np.ndarray | None = None
        self._index: pd.DatetimeIndex | None = None
        self._frequency = ""
        self._seed: int | None = None
        self._sigma = 0.0
        self._result: Any = None
        self._seasonal_periods: int | None = None

    def fit(
        self,
        timestamps: pd.Series | pd.DatetimeIndex,
        values: pd.Series | np.ndarray,
        *,
        frequency: str,
        seed: int | None = None,
    ) -> Self:
        index, y = copy_training(timestamps, values, frequency=frequency)
        if self._period_arg is not None:
            period = self._period_arg
        else:
            period = period_from_frequency(frequency)
        needed = ets_minimum_train_size(frequency=frequency, seasonal_period=self._period_arg)
        seasonal = None
        seasonal_periods = None
        if period is not None and period >= 2:
            if y.size < needed:
                msg = f"ETS seasonal needs at least {needed} observations; got {y.size}."
                raise ForecastInterfaceError(msg)
            seasonal = "add"
            seasonal_periods = int(period)
        elif y.size < needed:
            msg = f"ETS needs at least {needed} observations; got {y.size}."
            raise ForecastInterfaceError(msg)

        try:
            model = ExponentialSmoothing(
                y,
                trend="add",
                seasonal=seasonal,
                seasonal_periods=seasonal_periods,
                initialization_method="heuristic",
            )
            result = model.fit(optimized=True, use_brute=False, method="L-BFGS-B")
        except (ValueError, np.linalg.LinAlgError, RuntimeError) as exc:
            msg = f"ETS fit failed: {exc}"
            raise ForecastInterfaceError(msg) from exc

        resid = np.asarray(result.resid, dtype=float)
        self._sigma = residual_sigma(resid)
        self._result = result
        self._index = index
        self._y = y
        self._frequency = str(frequency).strip()
        self._seed = seed
        self._seasonal_periods = seasonal_periods
        self._fitted = True
        return self

    def predict(self, *, horizon: int) -> np.ndarray:
        require_fitted(self._fitted, "ETSModel")
        require_horizon(horizon)
        assert self._result is not None
        forecast = np.asarray(self._result.forecast(horizon), dtype=float)
        if forecast.size != horizon:
            msg = "ETS forecast length mismatch"
            raise ForecastInterfaceError(msg)
        return forecast.copy()

    def predict_interval(
        self,
        *,
        horizon: int,
        coverage: float = 0.95,
    ) -> tuple[np.ndarray, np.ndarray]:
        yhat = self.predict(horizon=horizon)
        return random_walk_intervals(yhat, self._sigma, coverage)

    def minimum_train_size(self, *, frequency: str) -> int:
        return ets_minimum_train_size(frequency=frequency, seasonal_period=self._period_arg)

    def metadata(self) -> ModelMetadata:
        require_fitted(self._fitted, "ETSModel")
        assert self._index is not None
        assert self._y is not None
        return ModelMetadata(
            model="ets",
            training_range=training_range_of(self._index),
            frequency=self._frequency,
            configuration={
                "trend": "add",
                "seasonal": "add" if self._seasonal_periods else None,
                "seasonal_periods": self._seasonal_periods,
                "initialization_method": "heuristic",
                "interval": "residual_sqrt_h",
                "seed_used": False,
            },
            random_seed=self._seed,
            n_train=int(self._y.size),
        )
