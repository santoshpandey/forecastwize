from __future__ import annotations

from datetime import UTC, datetime
from typing import Self

import numpy as np
import pandas as pd
import pytest
from app.forecasting.backtesting import (
    BacktestSpec,
    plan_backtest_folds,
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
from app.forecasting.metrics import mae, wis
from app.forecasting.naive import NaiveModel

from tests.ts_fixtures import daily_index


class _ConstantModel(ForecastModel):
    """Test double: always predicts `fill` with unit-width intervals."""

    def __init__(self, fill: float = 0.0) -> None:
        self._fill = fill
        self._fitted = False
        self._meta: ModelMetadata | None = None
        self.max_train_timestamp: pd.Timestamp | None = None
        self.n_train_seen = 0
        self.train_values: np.ndarray | None = None

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
        self.max_train_timestamp = stamp.max()
        self.n_train_seen = int(stamp.size)
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


class _BoomModel(_ConstantModel):
    def fit(
        self,
        timestamps: pd.Series | pd.DatetimeIndex,
        values: pd.Series | np.ndarray,
        *,
        frequency: str,
        seed: int | None = None,
    ) -> Self:
        raise RuntimeError("intentional fold failure")


def _spec(**kwargs: object) -> BacktestSpec:
    payload: dict[str, object] = {
        "frequency": "D",
        "horizon": 2,
        "min_train_size": 4,
        "window_type": "expanding",
        "step": 1,
        "coverage": 0.9,
        "seed": 7,
        "seasonality_period": 1,
    }
    payload.update(kwargs)
    return BacktestSpec.model_validate(payload)


def test_expanding_plans_have_no_overlap_or_future_in_train() -> None:
    plans = plan_backtest_folds(10, horizon=3, min_train_size=4, window_type="expanding", step=1)
    assert plans[0].train_start_index == 0
    assert plans[0].train_end_index == 3
    assert plans[0].test_start_index == 4
    assert plans[0].test_end_index == 6
    assert plans[-1].test_end_index == 9
    origins = [plan.train_end_index for plan in plans]
    assert origins == sorted(origins)
    assert origins == list(range(3, 7))
    for plan in plans:
        assert plan.test_start_index == plan.train_end_index + 1
        assert plan.train_start_index == 0
        assert plan.n_train == plan.train_end_index + 1
        train = set(range(plan.train_start_index, plan.train_end_index + 1))
        test = set(range(plan.test_start_index, plan.test_end_index + 1))
        assert train.isdisjoint(test)


def test_rolling_window_length_is_constant_and_slides() -> None:
    plans = plan_backtest_folds(
        12,
        horizon=2,
        min_train_size=3,
        window_type="rolling",
        rolling_window_size=4,
        step=2,
    )
    assert [plan.n_train for plan in plans] == [4, 4, 4, 4]
    assert [plan.train_start_index for plan in plans] == [0, 2, 4, 6]
    assert [plan.train_end_index for plan in plans] == [3, 5, 7, 9]
    for plan in plans:
        assert plan.test_end_index < 12
        assert plan.train_end_index < plan.test_start_index


def test_no_complete_folds_raises() -> None:
    with pytest.raises(ForecastInterfaceError, match="No complete backtest folds"):
        plan_backtest_folds(5, horizon=4, min_train_size=3, window_type="expanding")


def test_unsorted_and_duplicate_timestamps_are_rejected() -> None:
    stamps = daily_index(8)
    values = np.arange(8, dtype=float)
    spec = _spec()
    models = [("c", lambda: _ConstantModel(1.0))]
    reversed_stamps = stamps[::-1]
    with pytest.raises(ForecastInterfaceError, match="strictly increasing"):
        run_rolling_origin_backtest(reversed_stamps, values, models, spec)
    stamp_list = stamps.tolist()
    stamp_list[3] = stamp_list[2]
    dup = pd.DatetimeIndex(stamp_list)
    with pytest.raises(ForecastInterfaceError, match="unique"):
        run_rolling_origin_backtest(dup, values, models, spec)


def test_fit_never_sees_future_values_or_timestamps() -> None:
    n = 10
    stamps = daily_index(n)
    values = np.arange(n, dtype=float) + 3.0
    log: list[tuple[pd.DatetimeIndex, np.ndarray]] = []

    class _Spy(_ConstantModel):
        def fit(
            self,
            timestamps: pd.Series | pd.DatetimeIndex,
            values: pd.Series | np.ndarray,
            *,
            frequency: str,
            seed: int | None = None,
        ) -> _Spy:
            log.append(
                (
                    pd.DatetimeIndex(timestamps).copy(),
                    np.asarray(values, dtype=float).copy(),
                )
            )
            return super().fit(timestamps, values, frequency=frequency, seed=seed)

    spec = _spec(horizon=2, min_train_size=5)
    result = run_rolling_origin_backtest(
        stamps,
        values,
        [("spy", _Spy)],
        spec,
        generated_at=datetime(2021, 1, 1, tzinfo=UTC),
    )
    assert len(log) == len(result.folds_planned)
    for plan, (seen_index, seen_y) in zip(result.folds_planned, log, strict=True):
        expected_index = stamps[plan.train_start_index : plan.train_end_index + 1]
        expected_y = values[plan.train_start_index : plan.train_end_index + 1]
        pd.testing.assert_index_equal(seen_index, expected_index)
        np.testing.assert_array_equal(seen_y, expected_y)
        assert seen_index.max() == stamps[plan.train_end_index]
        assert seen_index.max() < stamps[plan.test_start_index]
        fold = result.results[0].folds[plan.fold_id]
        assert fold.train_end < fold.test_timestamps[0]


def test_does_not_mutate_caller_series() -> None:
    stamps = daily_index(8)
    values = np.arange(8, dtype=float)
    original_stamps = stamps.copy()
    original_values = values.copy()
    spec = _spec(min_train_size=4, horizon=2)
    run_rolling_origin_backtest(stamps, values, [("c", lambda: _ConstantModel(0.0))], spec)
    values[0] = 99.0
    pd.testing.assert_index_equal(stamps, original_stamps)
    np.testing.assert_array_equal(original_values, np.arange(8, dtype=float))


def test_expanding_and_rolling_are_deterministic() -> None:
    stamps = daily_index(12)
    values = np.linspace(1.0, 4.0, 12)
    generated = datetime(2022, 2, 2, tzinfo=UTC)
    models = [("low", lambda: _ConstantModel(1.0)), ("high", lambda: _ConstantModel(50.0))]
    expanding = _spec(window_type="expanding", min_train_size=5, horizon=2)
    a = run_rolling_origin_backtest(stamps, values, models, expanding, generated_at=generated)
    b = run_rolling_origin_backtest(stamps, values, models, expanding, generated_at=generated)
    assert a.model_dump() == b.model_dump()
    rolling = _spec(
        window_type="rolling",
        min_train_size=4,
        rolling_window_size=5,
        horizon=2,
    )
    c = run_rolling_origin_backtest(stamps, values, models, rolling, generated_at=generated)
    d = run_rolling_origin_backtest(stamps, values, models, rolling, generated_at=generated)
    assert c.model_dump() == d.model_dump()
    assert c.spec.window_type == "rolling"
    assert all(fold.n_train == 5 for fold in c.results[0].folds)


def test_multiple_models_share_identical_folds_and_rank_by_wis() -> None:
    stamps = daily_index(9)
    values = np.zeros(9)
    spec = _spec(min_train_size=4, horizon=2, coverage=0.9)
    comparison = run_rolling_origin_backtest(
        stamps,
        values,
        [("high", lambda: _ConstantModel(10.0)), ("low", lambda: _ConstantModel(0.0))],
        spec,
        generated_at=datetime(2020, 1, 1, tzinfo=UTC),
    )
    assert comparison.model_ids == ["high", "low"]
    assert [row.fold_id for row in comparison.results[0].folds] == [
        plan.fold_id for plan in comparison.folds_planned
    ]
    assert [row.train_end_index for row in comparison.results[0].folds] == [
        row.train_end_index for row in comparison.results[1].folds
    ]
    assert comparison.ranking[0].model_id == "low"
    assert comparison.ranking[0].rank == 1
    assert comparison.ranking[1].model_id == "high"
    assert comparison.ranking[1].rank == 2
    assert comparison.ranking[0].official_wis is not None
    assert comparison.ranking[1].official_wis is not None
    assert comparison.ranking[0].official_wis < comparison.ranking[1].official_wis
    fold0 = comparison.results[1].folds[0]
    assert fold0.status == "completed"
    assert fold0.metadata is not None
    assert fold0.metadata.model == "constant_0.0"
    assert fold0.metrics.wis == pytest.approx(
        wis(fold0.actual, fold0.yhat, fold0.lower, fold0.upper, coverage=0.9)
    )
    assert fold0.metrics.mae == pytest.approx(mae(fold0.actual, fold0.yhat))


def test_failed_folds_are_recorded_and_poison_official_mean() -> None:
    stamps = daily_index(8)
    values = np.arange(8, dtype=float)
    spec = _spec(min_train_size=4, horizon=2)
    comparison = run_rolling_origin_backtest(
        stamps,
        values,
        [("ok", lambda: _ConstantModel(1.0)), ("boom", _BoomModel)],
        spec,
        generated_at=datetime(2020, 5, 1, tzinfo=UTC),
    )
    ok = comparison.results[0]
    boom = comparison.results[1]
    assert ok.aggregate.n_folds_failed == 0
    assert ok.aggregate.wis is not None
    assert boom.aggregate.n_folds_failed == boom.aggregate.n_folds_planned
    assert boom.aggregate.n_folds_completed == 0
    assert boom.aggregate.wis is None
    assert boom.aggregate.wis_completed_only is None
    assert all(fold.status == "failed" for fold in boom.folds)
    assert boom.folds[0].error_type == "RuntimeError"
    assert "intentional" in (boom.folds[0].error_message or "")
    assert boom.folds[0].yhat is None
    unranked = [row for row in comparison.ranking if row.model_id == "boom"][0]
    assert unranked.rank is None
    assert unranked.n_folds_failed == boom.aggregate.n_folds_planned


def test_naive_backtest_matches_last_train_value() -> None:
    stamps = daily_index(8)
    values = np.array([1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0])
    spec = _spec(min_train_size=5, horizon=2)
    comparison = run_rolling_origin_backtest(
        stamps,
        values,
        [("naive", NaiveModel)],
        spec,
        generated_at=datetime(2020, 1, 1, tzinfo=UTC),
    )
    for fold in comparison.results[0].folds:
        last = values[fold.train_end_index]
        assert fold.yhat == [last, last]
        assert fold.metadata is not None
        assert fold.metadata.n_train == fold.n_train
        assert fold.metadata.frequency == "D"


def test_empty_or_duplicate_model_ids_rejected() -> None:
    stamps = daily_index(8)
    values = np.arange(8, dtype=float)
    spec = _spec()
    with pytest.raises(ForecastInterfaceError, match="non-empty"):
        run_rolling_origin_backtest(stamps, values, [], spec)
    with pytest.raises(ForecastInterfaceError, match="duplicate"):
        run_rolling_origin_backtest(
            stamps,
            values,
            [("a", lambda: _ConstantModel(0.0)), ("a", lambda: _ConstantModel(1.0))],
            spec,
        )


def test_rolling_window_size_rules() -> None:
    with pytest.raises(ValueError, match="rolling_window_size is required"):
        _spec(window_type="rolling")
    with pytest.raises(ValueError, match="must be omitted"):
        _spec(window_type="expanding", rolling_window_size=4)
    with pytest.raises(ValueError, match=">= min_train_size"):
        _spec(window_type="rolling", min_train_size=5, rolling_window_size=4)
