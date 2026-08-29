"""Fixed-order ARIMA / SARIMA baseline. Deterministic MLE. No auto-order search, no LLM."""

from __future__ import annotations

from typing import Any, Self

import numpy as np
import pandas as pd
from statsmodels.tsa.arima.model import ARIMA

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


class ARIMAModel(ForecastModel):
    """Non-seasonal ARIMA(1,1,1); if a seasonal period is known, airline SARIMA.

    Order is fixed (conventional specification, not agent or auto_arima selection).
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
        self._order: tuple[int, int, int] = (1, 1, 1)
        self._seasonal_order: tuple[int, int, int, int] = (0, 0, 0, 0)

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
        order = (1, 1, 1)
        seasonal_order = (0, 0, 0, 0)
        if period is not None and period >= 2:
            min_n = 2 * int(period) + 8
            if y.size < min_n:
                msg = f"Seasonal ARIMA needs at least {min_n} observations; got {y.size}."
                raise ForecastInterfaceError(msg)
            order = (0, 1, 1)
            seasonal_order = (0, 1, 1, int(period))
        elif y.size < 8:
            msg = f"ARIMA(1,1,1) needs at least 8 observations; got {y.size}."
            raise ForecastInterfaceError(msg)

        try:
            model = ARIMA(y, order=order, seasonal_order=seasonal_order, trend="n")
            result = model.fit(method_kwargs={"warn_convergence": False, "disp": False})
        except (ValueError, np.linalg.LinAlgError, RuntimeError) as exc:
            msg = f"ARIMA fit failed: {exc}"
            raise ForecastInterfaceError(msg) from exc

        resid = np.asarray(result.resid, dtype=float)
        self._sigma = residual_sigma(resid)
        self._result = result
        self._order = order
        self._seasonal_order = seasonal_order
        self._index = index
        self._y = y
        self._frequency = str(frequency).strip()
        self._seed = seed
        self._fitted = True
        return self

    def predict(self, *, horizon: int) -> np.ndarray:
        require_fitted(self._fitted, "ARIMAModel")
        require_horizon(horizon)
        assert self._result is not None
        fc = self._result.get_forecast(steps=horizon)
        mean = np.asarray(fc.predicted_mean, dtype=float).copy()
        if mean.size != horizon:
            msg = "ARIMA forecast length mismatch"
            raise ForecastInterfaceError(msg)
        return mean

    def predict_interval(
        self,
        *,
        horizon: int,
        coverage: float = 0.95,
    ) -> tuple[np.ndarray, np.ndarray]:
        yhat = self.predict(horizon=horizon)
        result = self._result
        try:
            fc = result.get_forecast(steps=horizon)
            frame = fc.conf_int(alpha=1.0 - coverage)
            values = np.asarray(frame, dtype=float)
            if values.ndim == 2 and values.shape[0] == horizon and values.shape[1] >= 2:
                return values[:, 0].copy(), values[:, 1].copy()
        except (ValueError, AttributeError, TypeError, IndexError):
            pass
        return random_walk_intervals(yhat, self._sigma, coverage)

    def metadata(self) -> ModelMetadata:
        require_fitted(self._fitted, "ARIMAModel")
        assert self._index is not None
        assert self._y is not None
        return ModelMetadata(
            model="arima",
            training_range=training_range_of(self._index),
            frequency=self._frequency,
            configuration={
                "order_p": self._order[0],
                "order_d": self._order[1],
                "order_q": self._order[2],
                "seasonal_P": self._seasonal_order[0],
                "seasonal_D": self._seasonal_order[1],
                "seasonal_Q": self._seasonal_order[2],
                "seasonal_m": self._seasonal_order[3],
                "selection": "fixed_specification",
                "seed_used": False,
            },
            random_seed=self._seed,
            n_train=int(self._y.size),
        )
