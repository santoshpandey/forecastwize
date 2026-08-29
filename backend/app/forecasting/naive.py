"""Last-observation-carried-forward naive forecast. Deterministic. No LLM."""

from __future__ import annotations

from typing import Self

import numpy as np
import pandas as pd

from app.forecasting._support import (
    copy_training,
    random_walk_intervals,
    require_fitted,
    require_horizon,
    residual_sigma,
    training_range_of,
)
from app.forecasting.base import ForecastModel, ModelMetadata


class NaiveModel(ForecastModel):
    """ŷ_{T+h} = y_T. Intervals use first-difference residual σ and √h growth."""

    def __init__(self) -> None:
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
        self._index = index
        self._y = y
        self._frequency = str(frequency).strip()
        self._seed = seed
        diffs = np.diff(y) if y.size >= 2 else np.array([], dtype=float)
        self._sigma = residual_sigma(diffs)
        self._fitted = True
        return self

    def predict(self, *, horizon: int) -> np.ndarray:
        require_fitted(self._fitted, "NaiveModel")
        require_horizon(horizon)
        assert self._y is not None
        return np.full(horizon, float(self._y[-1]), dtype=float)

    def predict_interval(
        self,
        *,
        horizon: int,
        coverage: float = 0.95,
    ) -> tuple[np.ndarray, np.ndarray]:
        yhat = self.predict(horizon=horizon)
        return random_walk_intervals(yhat, self._sigma, coverage)

    def metadata(self) -> ModelMetadata:
        require_fitted(self._fitted, "NaiveModel")
        assert self._index is not None
        assert self._y is not None
        return ModelMetadata(
            model="naive",
            training_range=training_range_of(self._index),
            frequency=self._frequency,
            configuration={
                "interval": "random_walk_residual",
                "seed_used": False,
            },
            random_seed=self._seed,
            n_train=int(self._y.size),
        )
