"""Forecasting interface, baseline models, metrics, and interval helpers. No FastAPI/LLM."""

from app.forecasting.arima import ARIMAModel
from app.forecasting.backtesting import (
    BacktestComparison,
    BacktestSpec,
    plan_backtest_folds,
    run_model_specific_origin_backtest,
    run_rolling_origin_backtest,
)
from app.forecasting.base import (
    ForecastInterfaceError,
    ForecastModel,
    ForecastResult,
    ModelMetadata,
    ModelNotFittedError,
    TrainingRange,
    assemble_forecast_result,
)
from app.forecasting.ets import ETSModel
from app.forecasting.intervals import (
    IntervalOrderError,
    assert_interval_order,
    coverage_to_alpha,
    symmetric_intervals,
)
from app.forecasting.metrics import (
    interval_coverage,
    interval_score,
    interval_width,
    mae,
    mase,
    rmse,
    smape,
    wis,
    wmape,
)
from app.forecasting.missing_policy import apply_linear_interpolate_train
from app.forecasting.naive import NaiveModel
from app.forecasting.seasonal_naive import SeasonalNaiveModel

__all__ = [
    "ARIMAModel",
    "BacktestComparison",
    "BacktestSpec",
    "ETSModel",
    "ForecastInterfaceError",
    "ForecastModel",
    "ForecastResult",
    "IntervalOrderError",
    "ModelMetadata",
    "ModelNotFittedError",
    "NaiveModel",
    "SeasonalNaiveModel",
    "TrainingRange",
    "assemble_forecast_result",
    "apply_linear_interpolate_train",
    "assert_interval_order",
    "coverage_to_alpha",
    "interval_coverage",
    "interval_score",
    "interval_width",
    "mae",
    "mase",
    "plan_backtest_folds",
    "rmse",
    "run_model_specific_origin_backtest",
    "run_rolling_origin_backtest",
    "smape",
    "symmetric_intervals",
    "wis",
    "wmape",
]
