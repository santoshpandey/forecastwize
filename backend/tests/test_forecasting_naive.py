from __future__ import annotations

import inspect

import numpy as np
import pandas as pd
import pytest
from app.forecasting import naive as naive_module
from app.forecasting.base import ForecastInterfaceError, ModelNotFittedError
from app.forecasting.naive import NaiveModel

from tests.ts_fixtures import daily_index


def test_naive_source_has_no_fastapi_or_llm() -> None:
    text = inspect.getsource(naive_module).lower()
    assert "import fastapi" not in text
    assert "import openai" not in text
    assert "langgraph" not in text


def test_unfitted_naive_raises() -> None:
    model = NaiveModel()
    with pytest.raises(ModelNotFittedError):
        model.predict(horizon=1)
    with pytest.raises(ModelNotFittedError):
        model.predict_interval(horizon=1)
    with pytest.raises(ModelNotFittedError):
        model.metadata()


def test_naive_is_last_observation_and_does_not_mutate() -> None:
    stamps = daily_index(6)
    values = np.array([1.0, 2.0, 3.0, 4.0, 5.0, 8.0])
    original = values.copy()
    model = NaiveModel()
    model.fit(stamps, values, frequency="D", seed=3)
    values[0] = -99.0
    np.testing.assert_array_equal(original, np.array([1.0, 2.0, 3.0, 4.0, 5.0, 8.0]))
    yhat = model.predict(horizon=4)
    np.testing.assert_allclose(yhat, np.full(4, 8.0))
    lower, upper = model.predict_interval(horizon=4, coverage=0.95)
    assert lower.shape == upper.shape == (4,)
    assert np.all(lower <= upper)
    meta = model.metadata()
    assert meta.model == "naive"
    assert meta.frequency == "D"
    assert meta.random_seed == 3
    assert meta.n_train == 6
    assert meta.training_range.start < meta.training_range.end


def test_naive_is_deterministic() -> None:
    stamps = daily_index(8)
    values = np.array([2.0, 2.5, 3.0, 2.8, 3.2, 3.1, 3.4, 3.3])
    first = NaiveModel().fit(stamps, values, frequency="D").predict(horizon=5)
    second = NaiveModel().fit(stamps, values, frequency="D").predict(horizon=5)
    np.testing.assert_array_equal(first, second)
    lo1, hi1 = NaiveModel().fit(stamps, values, frequency="D").predict_interval(horizon=5)
    lo2, hi2 = NaiveModel().fit(stamps, values, frequency="D").predict_interval(horizon=5)
    np.testing.assert_array_equal(lo1, lo2)
    np.testing.assert_array_equal(hi1, hi2)


def test_naive_rejects_empty_nan_and_bad_horizon() -> None:
    stamps = daily_index(3)
    with pytest.raises(ForecastInterfaceError, match="empty"):
        NaiveModel().fit(pd.DatetimeIndex([]), np.array([]), frequency="D")
    with pytest.raises(ForecastInterfaceError, match="non-finite"):
        NaiveModel().fit(stamps, np.array([1.0, np.nan, 2.0]), frequency="D")
    model = NaiveModel().fit(stamps, np.array([1.0, 2.0, 3.0]), frequency="D")
    with pytest.raises(ForecastInterfaceError, match="horizon"):
        model.predict(horizon=0)
