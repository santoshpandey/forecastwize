from __future__ import annotations

from datetime import UTC, datetime

import numpy as np
import pandas as pd
import pytest
from app.forecasting.base import (
    ForecastModel,
    ForecastResult,
    ModelMetadata,
    ModelNotFittedError,
    TrainingRange,
    _as_datetime_list,
    assemble_forecast_result,
)
from app.forecasting.intervals import IntervalOrderError, symmetric_intervals


class _StubMeanModel(ForecastModel):
    """Test double only. Not a production forecasting model."""

    def __init__(self) -> None:
        self._fitted = False
        self._mean = 0.0
        self._meta: ModelMetadata | None = None

    def fit(
        self,
        timestamps: pd.Series | pd.DatetimeIndex,
        values: pd.Series | np.ndarray,
        *,
        frequency: str,
        seed: int | None = None,
    ) -> _StubMeanModel:
        stamp = pd.DatetimeIndex(timestamps).copy()
        y = np.asarray(values, dtype=float).copy()
        finite = y[np.isfinite(y)]
        self._mean = float(np.mean(finite)) if finite.size else np.nan
        times = _as_datetime_list(stamp)
        self._meta = ModelMetadata(
            model="stub_mean",
            training_range=TrainingRange(start=times[0], end=times[-1]),
            frequency=frequency,
            configuration={"kind": "test_double"},
            random_seed=seed,
            n_train=int(stamp.size),
        )
        self._fitted = True
        return self

    def predict(self, *, horizon: int) -> np.ndarray:
        if not self._fitted:
            raise ModelNotFittedError("fit() first")
        if horizon < 1:
            msg = "horizon must be >= 1"
            raise ValueError(msg)
        return np.full(horizon, self._mean)

    def predict_interval(
        self,
        *,
        horizon: int,
        coverage: float = 0.95,
    ) -> tuple[np.ndarray, np.ndarray]:
        yhat = self.predict(horizon=horizon)
        return symmetric_intervals(yhat, half_width=1.0)

    def metadata(self) -> ModelMetadata:
        if self._meta is None:
            raise ModelNotFittedError("fit() first")
        return self._meta


def test_unfitted_stub_raises() -> None:
    model = _StubMeanModel()
    with pytest.raises(ModelNotFittedError):
        model.predict(horizon=1)
    with pytest.raises(ModelNotFittedError):
        model.metadata()


def test_stub_does_not_mutate_training_arrays() -> None:
    stamps = pd.date_range("2020-01-01", periods=5, freq="D", tz="UTC")
    values = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
    original_stamps = stamps.copy()
    original_values = values.copy()
    model = _StubMeanModel()
    model.fit(stamps, values, frequency="D", seed=7)
    values[0] = 99.0
    np.testing.assert_array_equal(original_values, np.array([1.0, 2.0, 3.0, 4.0, 5.0]))
    pd.testing.assert_index_equal(stamps, original_stamps)
    yhat = model.predict(horizon=3)
    assert yhat.shape == (3,)
    assert yhat[0] == pytest.approx(3.0)
    assert model.metadata().random_seed == 7
    assert model.metadata().frequency == "D"


def test_assemble_forecast_result() -> None:
    stamps = pd.date_range("2020-01-06", periods=2, freq="D", tz="UTC")
    train = pd.date_range("2020-01-01", periods=5, freq="D", tz="UTC")
    values = np.ones(5)
    model = _StubMeanModel().fit(train, values, frequency="D", seed=None)
    yhat = model.predict(horizon=2)
    lower, upper = model.predict_interval(horizon=2, coverage=0.9)
    result = assemble_forecast_result(
        timestamps=stamps,
        yhat=yhat,
        lower=lower,
        upper=upper,
        metadata=model.metadata(),
        forecast_horizon=2,
        interval_coverage_nominal=0.9,
        generated_at=datetime(2020, 1, 10, tzinfo=UTC),
    )
    assert isinstance(result, ForecastResult)
    assert result.forecast_horizon == 2
    assert result.frequency == "D"
    assert result.yhat == [1.0, 1.0]
    assert result.lower[0] < result.upper[0]
    payload = result.model_dump()
    assert "yhat" in payload


def test_forecast_result_rejects_interval_inversion() -> None:
    rng = TrainingRange(
        start=datetime(2020, 1, 1, tzinfo=UTC),
        end=datetime(2020, 1, 5, tzinfo=UTC),
    )
    with pytest.raises(ValueError, match="interval ordering"):
        ForecastResult(
            timestamps=[datetime(2020, 1, 6, tzinfo=UTC)],
            yhat=[0.0],
            lower=[1.0],
            upper=[0.0],
            model="x",
            training_range=rng,
            forecast_horizon=1,
            frequency="D",
            configuration={},
            random_seed=None,
            generated_at=datetime(2020, 1, 6, tzinfo=UTC),
            interval_coverage_nominal=0.95,
        )


def test_forecast_result_rejects_length_mismatch() -> None:
    rng = TrainingRange(
        start=datetime(2020, 1, 1, tzinfo=UTC),
        end=datetime(2020, 1, 5, tzinfo=UTC),
    )
    with pytest.raises(ValueError, match="length"):
        ForecastResult(
            timestamps=[datetime(2020, 1, 6, tzinfo=UTC)],
            yhat=[0.0, 1.0],
            lower=[0.0],
            upper=[1.0],
            model="x",
            training_range=rng,
            forecast_horizon=1,
            frequency="D",
            configuration={},
            random_seed=None,
            generated_at=datetime(2020, 1, 6, tzinfo=UTC),
            interval_coverage_nominal=0.95,
        )


def test_forecasting_package_has_no_fastapi_or_llm() -> None:
    import inspect

    from app.forecasting import (
        _support,
        arima,
        backtesting,
        base,
        ets,
        intervals,
        metrics,
        missing_policy,
        naive,
        seasonal_naive,
    )
    from app.services import forecast_service
    from app.tools import backtest_tools

    for module in (
        _support,
        arima,
        backtesting,
        backtest_tools,
        base,
        ets,
        forecast_service,
        intervals,
        metrics,
        missing_policy,
        naive,
        seasonal_naive,
    ):
        text = inspect.getsource(module).lower()
        assert "import fastapi" not in text
        assert "import openai" not in text
        assert "langgraph" not in text


def test_interval_order_error_from_helper() -> None:
    with pytest.raises(IntervalOrderError):
        from app.forecasting.intervals import assert_interval_order

        assert_interval_order([1.0], [0.0])
