from __future__ import annotations

import inspect
from datetime import UTC, datetime
from typing import Self

import numpy as np
import pandas as pd
import pytest
from app.forecasting.arima import ARIMAModel
from app.forecasting.backtesting import (
    BacktestSpec,
    expanding_origin_step,
    run_model_specific_origin_backtest,
    run_rolling_origin_backtest,
)
from app.forecasting.base import (
    ForecastInterfaceError,
    ForecastModel,
    ModelMetadata,
    ModelNotFittedError,
    TrainingRange,
    _as_datetime_list,
)
from app.forecasting.ets import ETSModel
from app.forecasting.naive import NaiveModel
from app.tools.forecasting_tools import compact_comparison

from tests.ts_fixtures import daily_index, trend_seasonal

pytestmark = pytest.mark.filterwarnings("ignore::UserWarning")


class _ConstantModel(ForecastModel):
    def __init__(self, fill: float = 0.0, *, min_train: int = 1) -> None:
        self._fill = fill
        self._min_train = min_train
        self._fitted = False
        self._meta: ModelMetadata | None = None
        self.max_train_index: int | None = None
        self.train_values: np.ndarray | None = None

    def minimum_train_size(self, *, frequency: str) -> int:
        super().minimum_train_size(frequency=frequency)
        return self._min_train

    def fit(
        self,
        timestamps: pd.Series | pd.DatetimeIndex,
        values: pd.Series | np.ndarray,
        *,
        frequency: str,
        seed: int | None = None,
    ) -> Self:
        stamp = pd.DatetimeIndex(timestamps).copy()
        y = np.asarray(values, dtype=float).copy()
        if y.size < self._min_train:
            msg = f"needs at least {self._min_train} observations; got {y.size}"
            raise ForecastInterfaceError(msg)
        self.max_train_index = int(stamp.size) - 1
        self.train_values = y
        times = _as_datetime_list(stamp)
        self._meta = ModelMetadata(
            model=f"constant_{self._fill}",
            training_range=TrainingRange(start=times[0], end=times[-1]),
            frequency=frequency,
            configuration={"fill": self._fill},
            random_seed=seed,
            n_train=int(stamp.size),
        )
        self._fitted = True
        return self

    def predict(self, *, horizon: int) -> np.ndarray:
        if not self._fitted:
            raise ModelNotFittedError("fit first")
        return np.full(horizon, self._fill)

    def predict_interval(
        self,
        *,
        horizon: int,
        coverage: float = 0.95,
    ) -> tuple[np.ndarray, np.ndarray]:
        yhat = self.predict(horizon=horizon)
        return yhat - 1.0, yhat + 1.0

    def metadata(self) -> ModelMetadata:
        if self._meta is None:
            raise ModelNotFittedError("fit first")
        return self._meta


class _FailingModel(_ConstantModel):
    def fit(
        self,
        timestamps: pd.Series | pd.DatetimeIndex,
        values: pd.Series | np.ndarray,
        *,
        frequency: str,
        seed: int | None = None,
    ) -> Self:
        super().fit(timestamps, values, frequency=frequency, seed=seed)
        raise RuntimeError("intentional planned-fold failure")


def _spec(**kwargs: object) -> BacktestSpec:
    payload: dict[str, object] = {
        "frequency": "D",
        "horizon": 2,
        "min_train_size": 4,
        "window_type": "expanding",
        "step": 1,
        "coverage": 0.9,
        "seed": 7,
        "seasonality_period": 7,
    }
    payload.update(kwargs)
    return BacktestSpec.model_validate(payload)


def test_valid_fold_planning_starts_at_model_minimum() -> None:
    n = 20
    comparison = run_model_specific_origin_backtest(
        daily_index(n),
        np.arange(n, dtype=float),
        [("need8", lambda: _ConstantModel(1.0, min_train=8))],
        _spec(),
        target_folds=5,
        generated_at=datetime(2021, 1, 1, tzinfo=UTC),
    )
    plan = comparison.model_origin_plans[0]
    assert plan.min_train_size == 8
    assert plan.eligible is True
    assert plan.folds_planned[0].n_train == 8
    assert all(fold.n_train >= 8 for fold in plan.folds_planned)
    assert all(item.reason == "insufficient_train" for item in plan.skipped_origins)
    assert plan.skipped_origins[-1].n_train == 7
    for fold in comparison.results[0].folds:
        assert fold.test_end_index < n
        assert fold.train_end_index < fold.test_start_index


def test_insufficient_history_is_planning_not_failed_execution() -> None:
    n = 16
    horizon = 7
    comparison = run_model_specific_origin_backtest(
        daily_index(n),
        trend_seasonal(n),
        [("arima", lambda: ARIMAModel(seasonal_period=7))],
        _spec(horizon=horizon, seasonality_period=7),
        target_folds=5,
        generated_at=datetime(2021, 1, 1, tzinfo=UTC),
    )
    plan = comparison.model_origin_plans[0]
    assert plan.min_train_size == 22
    assert plan.n_folds_planned == 0
    assert plan.eligible is False
    assert plan.ineligibility_reason == "insufficient_history"
    result = comparison.results[0]
    assert result.aggregate.n_folds_planned == 0
    assert result.aggregate.n_folds_failed == 0
    assert result.aggregate.wis is None
    assert comparison.ranking[0].rank is None
    assert plan.skipped_origins
    assert all(item.n_train < 22 for item in plan.skipped_origins)


def test_ets_seasonal_minimum_history_skips_short_origins() -> None:
    n = 40
    comparison = run_model_specific_origin_backtest(
        daily_index(n),
        trend_seasonal(n),
        [("ets", lambda: ETSModel(seasonal_period=7))],
        _spec(horizon=3),
        target_folds=5,
        generated_at=datetime(2021, 1, 1, tzinfo=UTC),
    )
    plan = comparison.model_origin_plans[0]
    assert plan.min_train_size == 16
    assert plan.folds_planned[0].n_train == 16
    assert comparison.results[0].aggregate.n_folds_failed == 0
    assert comparison.results[0].aggregate.wis is not None


def test_arima_seasonal_minimum_history_skips_short_origins() -> None:
    n = 50
    comparison = run_model_specific_origin_backtest(
        daily_index(n),
        trend_seasonal(n),
        [("arima", lambda: ARIMAModel(seasonal_period=7))],
        _spec(horizon=3),
        target_folds=5,
        generated_at=datetime(2021, 1, 1, tzinfo=UTC),
    )
    plan = comparison.model_origin_plans[0]
    assert plan.min_train_size == 22
    assert plan.folds_planned[0].n_train == 22
    assert comparison.results[0].aggregate.n_folds_failed == 0
    assert comparison.results[0].aggregate.wis is not None


def test_all_planned_folds_succeeding_yields_official_wis() -> None:
    n = 24
    comparison = run_model_specific_origin_backtest(
        daily_index(n),
        np.arange(n, dtype=float),
        [("ok", lambda: _ConstantModel(2.0, min_train=6))],
        _spec(),
        target_folds=4,
        generated_at=datetime(2021, 1, 1, tzinfo=UTC),
    )
    agg = comparison.results[0].aggregate
    assert agg.n_folds_planned == agg.n_folds_completed
    assert agg.n_folds_failed == 0
    assert agg.wis is not None
    assert agg.wis == agg.wis_completed_only


def test_planned_fold_execution_failure_keeps_official_wis_null() -> None:
    n = 20
    comparison = run_model_specific_origin_backtest(
        daily_index(n),
        np.arange(n, dtype=float),
        [("boom", lambda: _FailingModel(0.0, min_train=6))],
        _spec(),
        target_folds=3,
        generated_at=datetime(2021, 1, 1, tzinfo=UTC),
    )
    agg = comparison.results[0].aggregate
    assert agg.n_folds_planned >= 1
    assert agg.n_folds_failed == agg.n_folds_planned
    assert agg.wis is None
    assert agg.wis_completed_only is None
    assert comparison.ranking[0].official_wis is None


def test_no_holdout_leakage_in_model_specific_folds() -> None:
    n_train = 18
    holdout = np.full(5, 999.0)
    train = np.arange(n_train, dtype=float)
    spy_trains: list[np.ndarray] = []

    class _Spy(_ConstantModel):
        def fit(
            self,
            timestamps: pd.Series | pd.DatetimeIndex,
            values: pd.Series | np.ndarray,
            *,
            frequency: str,
            seed: int | None = None,
        ) -> Self:
            y = np.asarray(values, dtype=float).copy()
            spy_trains.append(y)
            assert 999.0 not in y.tolist()
            return super().fit(timestamps, values, frequency=frequency, seed=seed)

    comparison = run_model_specific_origin_backtest(
        daily_index(n_train),
        train,
        [("spy", lambda: _Spy(1.0, min_train=5))],
        _spec(horizon=3),
        target_folds=4,
        generated_at=datetime(2021, 1, 1, tzinfo=UTC),
    )
    assert holdout[0] == 999.0
    for fold in comparison.results[0].folds:
        assert fold.test_end_index < n_train
        assert fold.train_end_index < fold.test_start_index
    assert spy_trains
    for seen in spy_trains:
        assert seen.size < n_train or np.allclose(seen, train[: seen.size])
        assert seen.max() < 999.0


def test_baseline_shared_planning_is_unchanged() -> None:
    n = 30
    stamps = daily_index(n)
    values = trend_seasonal(n)
    spec = _spec(
        min_train_size=8, horizon=3, step=expanding_origin_step(n, horizon=3, min_train_size=8)
    )
    shared = run_rolling_origin_backtest(
        stamps,
        values,
        [("naive", NaiveModel), ("ets", lambda: ETSModel(seasonal_period=7))],
        spec,
        generated_at=datetime(2021, 1, 1, tzinfo=UTC),
    )
    assert shared.origin_planning == "shared"
    naive_ends = [fold.train_end_index for fold in shared.results[0].folds]
    ets_ends = [fold.train_end_index for fold in shared.results[1].folds]
    assert naive_ends == ets_ends
    assert shared.results[0].folds[0].n_train == 8
    ets_failed = shared.results[1].aggregate.n_folds_failed
    assert ets_failed >= 1
    assert shared.results[1].aggregate.wis is None
    source = inspect.getsource(inspect.getmodule(run_rolling_origin_backtest))
    assert "run_model_specific_origin_backtest" in source


def test_advanced_selection_uses_official_wis_not_completed_only() -> None:
    n = 24
    comparison = run_model_specific_origin_backtest(
        daily_index(n),
        np.arange(n, dtype=float),
        [
            ("unstable", lambda: _FailingModel(0.0, min_train=6)),
            ("stable", lambda: _ConstantModel(4.0, min_train=6)),
        ],
        _spec(),
        target_folds=3,
        generated_at=datetime(2021, 1, 1, tzinfo=UTC),
    )
    compact = compact_comparison(comparison, n_observations=n)
    by_id = {row.model_id: row for row in compact.candidates}
    assert by_id["unstable"].wis_completed_only is None
    assert by_id["unstable"].official_wis is None
    assert by_id["unstable"].rejection_reason == "planned_fold_failed"
    assert by_id["stable"].official_wis is not None
    assert by_id["stable"].n_folds_failed == 0
    assert by_id["stable"].rank == 1
    ranked = [row for row in compact.candidates if row.rank == 1]
    assert ranked[0].model_id == "stable"
    assert ranked[0].official_wis == by_id["stable"].official_wis


def test_deterministic_repeatability() -> None:
    n = 36
    stamps = daily_index(n)
    values = trend_seasonal(n)
    spec = _spec(horizon=3)
    generated = datetime(2021, 5, 1, tzinfo=UTC)
    models = [
        ("naive", NaiveModel),
        ("ets", lambda: ETSModel(seasonal_period=7)),
        ("arima", lambda: ARIMAModel(seasonal_period=7)),
    ]
    a = run_model_specific_origin_backtest(
        stamps, values, models, spec, target_folds=5, generated_at=generated
    )
    b = run_model_specific_origin_backtest(
        stamps, values, models, spec, target_folds=5, generated_at=generated
    )
    assert [p.model_dump(mode="json") for p in a.model_origin_plans] == [
        p.model_dump(mode="json") for p in b.model_origin_plans
    ]
    assert [(row.model_id, row.rank, row.official_wis) for row in a.ranking] == [
        (row.model_id, row.rank, row.official_wis) for row in b.ranking
    ]
    for left, right in zip(a.results, b.results, strict=True):
        assert left.aggregate.n_folds_planned == right.aggregate.n_folds_planned
        assert left.aggregate.n_folds_failed == right.aggregate.n_folds_failed
        if left.aggregate.wis is None:
            assert right.aggregate.wis is None
        else:
            assert right.aggregate.wis == pytest.approx(left.aggregate.wis)
    for result in a.results:
        if result.aggregate.n_folds_failed == 0 and result.aggregate.n_folds_planned > 0:
            assert result.aggregate.wis is not None


def test_baseline_harness_does_not_import_model_specific_runner() -> None:
    from evaluation import run_baseline

    text = inspect.getsource(run_baseline)
    assert "run_model_specific_origin_backtest" not in text
    assert "run_rolling_origin_backtest" in text
