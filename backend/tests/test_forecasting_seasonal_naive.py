from __future__ import annotations

import inspect

import numpy as np
import pytest
from app.forecasting import seasonal_naive as seasonal_naive_module
from app.forecasting.base import ForecastInterfaceError, ModelNotFittedError
from app.forecasting.seasonal_naive import SeasonalNaiveModel

from tests.ts_fixtures import daily_index


def test_seasonal_naive_source_has_no_fastapi_or_llm() -> None:
    text = inspect.getsource(seasonal_naive_module).lower()
    assert "import fastapi" not in text
    assert "import openai" not in text
    assert "langgraph" not in text


def test_unfitted_seasonal_naive_raises() -> None:
    model = SeasonalNaiveModel(seasonal_period=4)
    with pytest.raises(ModelNotFittedError):
        model.predict(horizon=1)
    with pytest.raises(ModelNotFittedError):
        model.metadata()


def test_seasonal_naive_repeats_last_cycle() -> None:
    stamps = daily_index(8)
    values = np.array([1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0])
    original = values.copy()
    model = SeasonalNaiveModel(seasonal_period=4)
    model.fit(stamps, values, frequency="D")
    values[-1] = 99.0
    np.testing.assert_array_equal(original, np.array([1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0]))
    yhat = model.predict(horizon=6)
    np.testing.assert_allclose(yhat, np.array([5.0, 6.0, 7.0, 8.0, 5.0, 6.0]))
    lower, upper = model.predict_interval(horizon=6, coverage=0.9)
    assert np.all(lower <= upper)
    meta = model.metadata()
    assert meta.model == "seasonal_naive"
    assert meta.frequency == "D"
    assert meta.configuration["seasonal_period"] == 4
    assert meta.random_seed is None


def test_seasonal_naive_infers_weekly_period_from_daily_frequency() -> None:
    stamps = daily_index(14)
    values = np.arange(14, dtype=float)
    model = SeasonalNaiveModel()
    model.fit(stamps, values, frequency="D")
    yhat = model.predict(horizon=7)
    np.testing.assert_allclose(yhat, values[-7:])
    assert model.metadata().configuration["seasonal_period"] == 7


def test_seasonal_naive_is_deterministic() -> None:
    stamps = daily_index(12)
    values = np.array([1.0, 3.0, 2.0, 4.0] * 3)
    a = SeasonalNaiveModel(seasonal_period=4).fit(stamps, values, frequency="D").predict(horizon=8)
    b = SeasonalNaiveModel(seasonal_period=4).fit(stamps, values, frequency="D").predict(horizon=8)
    np.testing.assert_array_equal(a, b)


def test_seasonal_naive_rejects_short_series_and_unknown_frequency() -> None:
    stamps = daily_index(3)
    with pytest.raises(ForecastInterfaceError, match="at least"):
        SeasonalNaiveModel(seasonal_period=4).fit(stamps, np.array([1.0, 2.0, 3.0]), frequency="D")
    stamps7 = daily_index(7)
    with pytest.raises(ForecastInterfaceError, match="seasonal_period"):
        SeasonalNaiveModel().fit(stamps7, np.arange(7, dtype=float), frequency="B")
