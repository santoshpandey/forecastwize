from __future__ import annotations

import inspect

import numpy as np
import pytest
from app.forecasting import arima as arima_module
from app.forecasting.arima import ARIMAModel
from app.forecasting.base import ForecastInterfaceError, ModelNotFittedError

from tests.ts_fixtures import daily_index, trend_seasonal

pytestmark = pytest.mark.filterwarnings("ignore::UserWarning")


def test_arima_source_has_no_fastapi_or_llm() -> None:
    text = inspect.getsource(arima_module).lower()
    assert "import fastapi" not in text
    assert "import openai" not in text
    assert "langgraph" not in text


def test_unfitted_arima_raises() -> None:
    model = ARIMAModel()
    with pytest.raises(ModelNotFittedError):
        model.predict(horizon=1)
    with pytest.raises(ModelNotFittedError):
        model.metadata()


def test_arima111_is_deterministic_and_does_not_mutate() -> None:
    n = 24
    stamps = daily_index(n)
    values = 4.0 + 0.25 * np.arange(n, dtype=float)
    original = values.copy()
    model = ARIMAModel()
    model.fit(stamps, values, frequency="B", seed=2)
    values[0] = 999.0
    np.testing.assert_array_equal(original, 4.0 + 0.25 * np.arange(n, dtype=float))
    yhat = model.predict(horizon=5)
    assert yhat.shape == (5,)
    assert np.all(np.isfinite(yhat))
    again = ARIMAModel().fit(stamps, original, frequency="B", seed=2).predict(horizon=5)
    np.testing.assert_allclose(yhat, again, rtol=0.0, atol=1e-8)
    lower, upper = model.predict_interval(horizon=5, coverage=0.95)
    assert np.all(lower <= upper)
    meta = model.metadata()
    assert meta.model == "arima"
    assert meta.frequency == "B"
    assert meta.configuration["order_p"] == 1
    assert meta.configuration["order_d"] == 1
    assert meta.configuration["order_q"] == 1
    assert meta.configuration["seasonal_m"] == 0
    assert meta.configuration["selection"] == "fixed_specification"
    assert meta.random_seed == 2


def test_airline_sarima_fixed_spec() -> None:
    n = 24
    stamps = daily_index(n)
    values = trend_seasonal(n, period=4)
    model = ARIMAModel(seasonal_period=4)
    model.fit(stamps, values, frequency="B")
    yhat = model.predict(horizon=4)
    assert yhat.shape == (4,)
    assert np.all(np.isfinite(yhat))
    meta = model.metadata()
    assert meta.configuration["order_p"] == 0
    assert meta.configuration["seasonal_P"] == 0
    assert meta.configuration["seasonal_D"] == 1
    assert meta.configuration["seasonal_Q"] == 1
    assert meta.configuration["seasonal_m"] == 4
    lower, upper = model.predict_interval(horizon=4)
    assert np.all(lower <= upper)


def test_arima_rejects_short_series() -> None:
    stamps = daily_index(5)
    with pytest.raises(ForecastInterfaceError, match="at least"):
        ARIMAModel().fit(stamps, np.arange(5, dtype=float), frequency="B")
