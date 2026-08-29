"""Seasonal naive forecast. Deterministic. No LLM."""

from __future__ import annotations

from typing import Self

import numpy as np
import pandas as pd

from app.data.seasonality import period_from_frequency
from app.forecasting._support import (
    copy_training,
    require_fitted,
    require_horizon,
    residual_sigma,
    seasonal_naive_intervals,
    training_range_of,
)
from app.forecasting.base import ForecastInterfaceError, ForecastModel, ModelMetadata


class SeasonalNaiveModel(ForecastModel):
    """ŷ_{T+h} = y_{T+h-m}. Period is constructor arg or inferred from frequency."""

    def __init__(self, *, seasonal_period: int | None = None) -> None:
        self._period_arg = seasonal_period
        self._period = 0
        self._fitted = False
        self._y: np.ndarray | None = None
        self._index: pd.DatetimeIndex | None = None
        self._frequency = ""
        self._seed: int | None = None
        self._sigma = 0.0

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
        if period is None or period < 2:
            msg = (
                "Seasonal naive needs seasonal_period>=2 or a frequency with a known "
                "period (D→7, h→24, MS/ME→12, W*→52)."
            )
            raise ForecastInterfaceError(msg)
        if y.size < period:
            msg = f"Seasonal naive needs at least {period} observations; got {y.size}."
            raise ForecastInterfaceError(msg)
        self._period = int(period)
        self._index = index
        self._y = y
        self._frequency = str(frequency).strip()
        self._seed = seed
        resid = y[period:] - y[:-period]
        self._sigma = residual_sigma(resid)
        self._fitted = True
        return self

    def predict(self, *, horizon: int) -> np.ndarray:
        require_fitted(self._fitted, "SeasonalNaiveModel")
        require_horizon(horizon)
        assert self._y is not None
        out = np.empty(horizon, dtype=float)
        for h in range(1, horizon + 1):
            out[h - 1] = float(self._y[-self._period + ((h - 1) % self._period)])
        return out

    def predict_interval(
        self,
        *,
        horizon: int,
        coverage: float = 0.95,
    ) -> tuple[np.ndarray, np.ndarray]:
        yhat = self.predict(horizon=horizon)
        return seasonal_naive_intervals(yhat, self._sigma, coverage, self._period)

    def metadata(self) -> ModelMetadata:
        require_fitted(self._fitted, "SeasonalNaiveModel")
        assert self._index is not None
        assert self._y is not None
        return ModelMetadata(
            model="seasonal_naive",
            training_range=training_range_of(self._index),
            frequency=self._frequency,
            configuration={
                "seasonal_period": self._period,
                "interval": "seasonal_naive_residual",
                "seed_used": False,
            },
            random_seed=self._seed,
            n_train=int(self._y.size),
        )
