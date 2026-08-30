from __future__ import annotations

import numpy as np
import pytest
from app.forecasting.arima import ARIMAModel, arima_minimum_train_size
from app.forecasting.base import ForecastInterfaceError
from app.forecasting.ets import ETSModel, ets_minimum_train_size
from app.forecasting.naive import NaiveModel
from app.forecasting.seasonal_naive import SeasonalNaiveModel, seasonal_naive_minimum_train_size
from app.services.forecast_service import create_baseline_model, minimum_train_size_for

from tests.ts_fixtures import daily_index, trend_seasonal

pytestmark = pytest.mark.filterwarnings("ignore::UserWarning")


def test_naive_minimum_is_one() -> None:
    assert NaiveModel().minimum_train_size(frequency="D") == 1
    assert minimum_train_size_for("naive", frequency="D") == 1
    stamps = daily_index(1)
    NaiveModel().fit(stamps, np.array([3.0]), frequency="D")


def test_seasonal_naive_minimum_matches_fit() -> None:
    assert seasonal_naive_minimum_train_size(frequency="D", seasonal_period=None) == 7
    assert SeasonalNaiveModel().minimum_train_size(frequency="D") == 7
    assert SeasonalNaiveModel(seasonal_period=4).minimum_train_size(frequency="B") == 4
    stamps = daily_index(6)
    with pytest.raises(ForecastInterfaceError, match="at least 7"):
        SeasonalNaiveModel().fit(stamps, np.arange(6, dtype=float), frequency="D")
    SeasonalNaiveModel().fit(daily_index(7), np.arange(7, dtype=float), frequency="D")


def test_ets_seasonal_minimum_matches_fit() -> None:
    assert ets_minimum_train_size(frequency="D", seasonal_period=None) == 16
    assert ETSModel().minimum_train_size(frequency="D") == 16
    assert ets_minimum_train_size(frequency="B", seasonal_period=None) == 3
    stamps = daily_index(15)
    with pytest.raises(ForecastInterfaceError, match="at least 16"):
        ETSModel().fit(stamps, trend_seasonal(15), frequency="D")
    ETSModel().fit(daily_index(16), trend_seasonal(16), frequency="D")


def test_arima_seasonal_minimum_matches_fit() -> None:
    assert arima_minimum_train_size(frequency="D", seasonal_period=None) == 22
    assert ARIMAModel().minimum_train_size(frequency="D") == 22
    assert arima_minimum_train_size(frequency="B", seasonal_period=None) == 8
    stamps = daily_index(21)
    with pytest.raises(ForecastInterfaceError, match="at least 22"):
        ARIMAModel().fit(stamps, trend_seasonal(21), frequency="D")
    ARIMAModel().fit(daily_index(22), trend_seasonal(22), frequency="D")


def test_minimum_train_size_for_uses_the_model() -> None:
    assert minimum_train_size_for("ets", frequency="D", seasonal_period=7) == 16
    assert minimum_train_size_for("arima", frequency="D", seasonal_period=7) == 22
    model = create_baseline_model("ets", seasonal_period=12)
    assert model.minimum_train_size(frequency="MS") == 24
