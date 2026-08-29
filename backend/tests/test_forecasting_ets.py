from __future__ import annotations

import inspect

import numpy as np
import pytest
from app.forecasting import ets as ets_module
from app.forecasting.base import ForecastInterfaceError, ModelNotFittedError
from app.forecasting.ets import ETSModel

from tests.ts_fixtures import daily_index, trend_seasonal

pytestmark = pytest.mark.filterwarnings("ignore::UserWarning")


def test_ets_source_has_no_fastapi_or_llm() -> None:
    text = inspect.getsource(ets_module).lower()
    assert "import fastapi" not in text
    assert "import openai" not in text
    assert "langgraph" not in text


def test_unfitted_ets_raises() -> None:
    model = ETSModel()
    with pytest.raises(ModelNotFittedError):
        model.predict(horizon=1)
    with pytest.raises(ModelNotFittedError):
        model.metadata()


def test_ets_holt_is_deterministic_and_does_not_mutate() -> None:
    n = 20
    stamps = daily_index(n)
    values = 5.0 + 0.3 * np.arange(n, dtype=float)
    original = values.copy()
    model = ETSModel()
    model.fit(stamps, values, frequency="B", seed=11)
    values[-1] = -1.0
    np.testing.assert_array_equal(original, 5.0 + 0.3 * np.arange(n, dtype=float))
    yhat = model.predict(horizon=4)
    assert yhat.shape == (4,)
    assert np.all(np.isfinite(yhat))
    again = ETSModel().fit(stamps, original, frequency="B", seed=11).predict(horizon=4)
    np.testing.assert_allclose(yhat, again, rtol=0.0, atol=1e-10)
    lower, upper = model.predict_interval(horizon=4, coverage=0.95)
    assert np.all(lower <= upper)
    meta = model.metadata()
    assert meta.model == "ets"
    assert meta.frequency == "B"
    assert meta.configuration["trend"] == "add"
    assert meta.configuration["seasonal"] is None
    assert meta.random_seed == 11
    assert meta.n_train == n


def test_ets_additive_seasonal_runs() -> None:
    n = 28
    stamps = daily_index(n)
    values = trend_seasonal(n, period=7)
    model = ETSModel()
    model.fit(stamps, values, frequency="D")
    yhat = model.predict(horizon=7)
    assert yhat.shape == (7,)
    assert np.all(np.isfinite(yhat))
    assert model.metadata().configuration["seasonal_periods"] == 7
    lower, upper = model.predict_interval(horizon=7)
    assert np.all(lower <= upper)


def test_ets_rejects_too_short_seasonal() -> None:
    stamps = daily_index(10)
    with pytest.raises(ForecastInterfaceError, match="at least"):
        ETSModel().fit(stamps, trend_seasonal(10), frequency="D")
