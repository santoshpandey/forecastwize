"""Rolling-origin backtesting. Time-aware splits only. No HTTP, LLM, or model selection."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from typing import Literal, Self

import numpy as np
import pandas as pd
from pydantic import BaseModel, ConfigDict, Field, field_serializer, model_validator

from app.forecasting.base import (
    ConfigValue,
    ForecastInterfaceError,
    ForecastModel,
    ModelMetadata,
    _as_datetime_list,
)
from app.forecasting.metrics import (
    interval_coverage,
    interval_width,
    mae,
    mase,
    rmse,
    smape,
    wis,
    wmape,
)

WindowType = Literal["expanding", "rolling"]
FoldStatus = Literal["completed", "failed"]
ModelFactory = Callable[[], ForecastModel]


def _to_utc_iso(value: datetime) -> str:
    aware = value if value.tzinfo is not None else value.replace(tzinfo=UTC)
    return aware.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _finite_or_none(value: float) -> float | None:
    if not np.isfinite(value):
        return None
    return float(value)


class BacktestFoldPlan(BaseModel):
    """One complete origin. Train end is strictly before the first test timestamp."""

    model_config = ConfigDict(extra="forbid")

    fold_id: int
    train_start_index: int
    train_end_index: int
    test_start_index: int
    test_end_index: int

    @model_validator(mode="after")
    def leakage_safe_indices(self) -> Self:
        if self.fold_id < 0:
            msg = "fold_id must be >= 0"
            raise ValueError(msg)
        if self.train_start_index < 0 or self.train_end_index < self.train_start_index:
            msg = "train indices are invalid"
            raise ValueError(msg)
        if self.test_start_index != self.train_end_index + 1:
            msg = "test must start at the first step after train_end (no gap, no overlap)"
            raise ValueError(msg)
        if self.test_end_index < self.test_start_index:
            msg = "test_end_index must be >= test_start_index"
            raise ValueError(msg)
        return self

    @property
    def n_train(self) -> int:
        return self.train_end_index - self.train_start_index + 1

    @property
    def horizon(self) -> int:
        return self.test_end_index - self.test_start_index + 1


class FoldMetrics(BaseModel):
    """Point and interval scores for one fold. None means undefined or fold failed."""

    model_config = ConfigDict(extra="forbid")

    mae: float | None
    rmse: float | None
    smape: float | None
    wmape: float | None
    mase: float | None
    wis: float | None
    interval_coverage: float | None
    interval_width: float | None


class BacktestFoldResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    fold_id: int
    status: FoldStatus
    train_start_index: int
    train_end_index: int
    test_start_index: int
    test_end_index: int
    n_train: int
    train_start: datetime
    train_end: datetime
    test_timestamps: list[datetime]
    actual: list[float] | None
    yhat: list[float] | None
    lower: list[float] | None
    upper: list[float] | None
    metrics: FoldMetrics
    metadata: ModelMetadata | None
    error_type: str | None = None
    error_message: str | None = None

    @field_serializer("train_start", "train_end")
    def serialize_bounds(self, value: datetime) -> str:
        return _to_utc_iso(value)

    @field_serializer("test_timestamps")
    def serialize_test_times(self, value: list[datetime]) -> list[str]:
        return [_to_utc_iso(item) for item in value]


class BacktestAggregate(BaseModel):
    """Official means use every planned fold. Failed folds make official means None.

    ``*_completed_only`` averages finite scores on completed folds and is labeled;
    it is not the headline comparison statistic.
    """

    model_config = ConfigDict(extra="forbid")

    n_folds_planned: int
    n_folds_completed: int
    n_folds_failed: int
    wis: float | None = Field(description="Official mean WIS over all planned folds.")
    mae: float | None
    rmse: float | None
    smape: float | None
    wmape: float | None
    mase: float | None
    interval_coverage: float | None
    interval_width: float | None
    wis_completed_only: float | None
    mae_completed_only: float | None
    rmse_completed_only: float | None
    smape_completed_only: float | None
    wmape_completed_only: float | None
    mase_completed_only: float | None
    interval_coverage_completed_only: float | None
    interval_width_completed_only: float | None


class ModelBacktestResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    model_id: str
    folds: list[BacktestFoldResult]
    aggregate: BacktestAggregate
    last_completed_metadata: ModelMetadata | None


class ModelRankingRow(BaseModel):
    """Deterministic ranking by official WIS (lower is better). Not a forecast."""

    model_config = ConfigDict(extra="forbid")

    rank: int | None
    model_id: str
    official_wis: float | None
    n_folds_failed: int


class BacktestSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    frequency: str
    horizon: int
    min_train_size: int
    window_type: WindowType
    rolling_window_size: int | None = None
    step: int = 1
    coverage: float = 0.95
    seed: int | None = None
    seasonality_period: int = 1

    @model_validator(mode="after")
    def valid_spec(self) -> Self:
        if not self.frequency.strip():
            msg = "frequency must be a non-empty explicit alias"
            raise ValueError(msg)
        if self.horizon < 1:
            msg = "horizon must be >= 1"
            raise ValueError(msg)
        if self.min_train_size < 1:
            msg = "min_train_size must be >= 1"
            raise ValueError(msg)
        if self.step < 1:
            msg = "step must be >= 1"
            raise ValueError(msg)
        if not 0.0 < self.coverage < 1.0:
            msg = "coverage must be in (0, 1)"
            raise ValueError(msg)
        if self.seasonality_period < 1:
            msg = "seasonality_period must be >= 1"
            raise ValueError(msg)
        if self.window_type == "rolling":
            if self.rolling_window_size is None:
                msg = "rolling_window_size is required when window_type='rolling'"
                raise ValueError(msg)
            if self.rolling_window_size < self.min_train_size:
                msg = "rolling_window_size must be >= min_train_size"
                raise ValueError(msg)
        elif self.rolling_window_size is not None:
            msg = "rolling_window_size must be omitted when window_type='expanding'"
            raise ValueError(msg)
        return self


class BacktestComparison(BaseModel):
    """Same splits for every model. Ranking is evidence, not an emitted forecast."""

    model_config = ConfigDict(extra="forbid")

    spec: BacktestSpec
    n_observations: int
    model_ids: list[str]
    folds_planned: list[BacktestFoldPlan]
    results: list[ModelBacktestResult]
    ranking: list[ModelRankingRow]
    generated_at: datetime
    configuration: dict[str, ConfigValue]

    @field_serializer("generated_at")
    def serialize_generated_at(self, value: datetime) -> str:
        return _to_utc_iso(value)


def plan_backtest_folds(
    n_observations: int,
    *,
    horizon: int,
    min_train_size: int,
    window_type: WindowType,
    rolling_window_size: int | None = None,
    step: int = 1,
) -> list[BacktestFoldPlan]:
    """Build complete rolling-origin folds. Incomplete tails are not planned.

    Expanding: train is ``[0, origin]``. Rolling: train is
    ``[origin - rolling_window_size + 1, origin]``. Test is always
    ``[origin + 1, origin + horizon]``. Origins advance by ``step``.
    """
    spec = BacktestSpec(
        frequency="D",
        horizon=horizon,
        min_train_size=min_train_size,
        window_type=window_type,
        rolling_window_size=rolling_window_size,
        step=step,
    )
    return _plan_folds(n_observations, spec)


def run_rolling_origin_backtest(
    timestamps: pd.Series | pd.DatetimeIndex,
    values: pd.Series | np.ndarray,
    models: Sequence[tuple[str, ModelFactory]],
    spec: BacktestSpec,
    *,
    generated_at: datetime | None = None,
) -> BacktestComparison:
    """Fit each factory on train-only slices and score the next ``horizon`` points.

    Failed folds are kept in the record. Official aggregate means are None if any
    planned fold failed or a metric is undefined. Does not select a production
    model and does not call an LLM.
    """
    index, y = _copy_backtest_inputs(timestamps, values, frequency=spec.frequency)
    n = int(index.size)
    factories = _validate_models(models)
    plans = _plan_folds(n, spec)
    created = generated_at if generated_at is not None else datetime.now(UTC)
    times = _as_datetime_list(index)

    results: list[ModelBacktestResult] = []
    for model_id, factory in factories:
        fold_rows: list[BacktestFoldResult] = []
        last_meta: ModelMetadata | None = None
        for plan in plans:
            row = _run_one_fold(
                plan=plan,
                index=index,
                y=y,
                times=times,
                factory=factory,
                spec=spec,
            )
            if row.status == "completed" and row.metadata is not None:
                last_meta = row.metadata
            fold_rows.append(row)
        results.append(
            ModelBacktestResult(
                model_id=model_id,
                folds=fold_rows,
                aggregate=_aggregate_folds(fold_rows, n_planned=len(plans)),
                last_completed_metadata=last_meta,
            )
        )

    ranking = _rank_by_official_wis(results)
    return BacktestComparison(
        spec=spec,
        n_observations=n,
        model_ids=[item[0] for item in factories],
        folds_planned=plans,
        results=results,
        ranking=ranking,
        generated_at=created,
        configuration={
            "window_type": spec.window_type,
            "horizon": spec.horizon,
            "min_train_size": spec.min_train_size,
            "rolling_window_size": spec.rolling_window_size,
            "step": spec.step,
            "coverage": spec.coverage,
            "seed": spec.seed,
            "seasonality_period": spec.seasonality_period,
            "selection": "none_comparison_only",
        },
    )


def _plan_folds(n_observations: int, spec: BacktestSpec) -> list[BacktestFoldPlan]:
    if n_observations < 1:
        msg = "series is empty"
        raise ForecastInterfaceError(msg)
    last_origin = n_observations - 1 - spec.horizon
    if spec.window_type == "expanding":
        first_origin = spec.min_train_size - 1
    else:
        assert spec.rolling_window_size is not None
        first_origin = spec.rolling_window_size - 1
    if first_origin > last_origin:
        msg = (
            f"No complete backtest folds: first origin {first_origin} > last origin "
            f"{last_origin} (n={n_observations}, horizon={spec.horizon}, "
            f"min_train_size={spec.min_train_size}, window_type={spec.window_type!r})."
        )
        raise ForecastInterfaceError(msg)

    plans: list[BacktestFoldPlan] = []
    fold_id = 0
    origin = first_origin
    while origin <= last_origin:
        if spec.window_type == "expanding":
            train_start = 0
        else:
            assert spec.rolling_window_size is not None
            train_start = origin - spec.rolling_window_size + 1
        test_start = origin + 1
        test_end = origin + spec.horizon
        plans.append(
            BacktestFoldPlan(
                fold_id=fold_id,
                train_start_index=train_start,
                train_end_index=origin,
                test_start_index=test_start,
                test_end_index=test_end,
            )
        )
        fold_id += 1
        origin += spec.step
    if not plans:
        msg = "No complete backtest folds after applying step"
        raise ForecastInterfaceError(msg)
    return plans


def _copy_backtest_inputs(
    timestamps: pd.Series | pd.DatetimeIndex,
    values: pd.Series | np.ndarray,
    *,
    frequency: str,
) -> tuple[pd.DatetimeIndex, np.ndarray]:
    if not frequency or not str(frequency).strip():
        msg = "frequency must be a non-empty explicit alias"
        raise ForecastInterfaceError(msg)
    index = pd.DatetimeIndex(timestamps).copy()
    y = np.asarray(values, dtype=float).copy()
    if index.size != y.size:
        msg = f"timestamps length {index.size} != values length {y.size}"
        raise ForecastInterfaceError(msg)
    if y.size == 0:
        msg = "series is empty"
        raise ForecastInterfaceError(msg)
    if not index.is_unique:
        msg = "timestamps must be unique; duplicates would make origin order ambiguous"
        raise ForecastInterfaceError(msg)
    if not index.is_monotonic_increasing:
        msg = (
            "timestamps must be strictly increasing; the backtester does not sort "
            "or shuffle the series"
        )
        raise ForecastInterfaceError(msg)
    return index, y


def _validate_models(
    models: Sequence[tuple[str, ModelFactory]],
) -> list[tuple[str, ModelFactory]]:
    if not models:
        msg = "models must be a non-empty sequence of (model_id, factory) pairs"
        raise ForecastInterfaceError(msg)
    seen: set[str] = set()
    out: list[tuple[str, ModelFactory]] = []
    for item in models:
        if not isinstance(item, tuple) or len(item) != 2:
            msg = "each model entry must be (model_id, factory)"
            raise ForecastInterfaceError(msg)
        model_id, factory = item
        key = str(model_id).strip()
        if not key:
            msg = "model_id must be non-empty"
            raise ForecastInterfaceError(msg)
        if key in seen:
            msg = f"duplicate model_id={key!r}"
            raise ForecastInterfaceError(msg)
        if not callable(factory):
            msg = f"factory for {key!r} must be callable"
            raise ForecastInterfaceError(msg)
        seen.add(key)
        out.append((key, factory))
    return out


def _run_one_fold(
    *,
    plan: BacktestFoldPlan,
    index: pd.DatetimeIndex,
    y: np.ndarray,
    times: list[datetime],
    factory: ModelFactory,
    spec: BacktestSpec,
) -> BacktestFoldResult:
    train_start = times[plan.train_start_index]
    train_end = times[plan.train_end_index]
    test_times = times[plan.test_start_index : plan.test_end_index + 1]
    base_kwargs = {
        "fold_id": plan.fold_id,
        "train_start_index": plan.train_start_index,
        "train_end_index": plan.train_end_index,
        "test_start_index": plan.test_start_index,
        "test_end_index": plan.test_end_index,
        "n_train": plan.n_train,
        "train_start": train_start,
        "train_end": train_end,
        "test_timestamps": test_times,
    }
    empty_metrics = FoldMetrics(
        mae=None,
        rmse=None,
        smape=None,
        wmape=None,
        mase=None,
        wis=None,
        interval_coverage=None,
        interval_width=None,
    )
    train_index = index[plan.train_start_index : plan.train_end_index + 1].copy()
    train_y = np.asarray(y[plan.train_start_index : plan.train_end_index + 1], dtype=float).copy()
    actual = np.asarray(y[plan.test_start_index : plan.test_end_index + 1], dtype=float).copy()
    try:
        if train_end >= test_times[0]:
            msg = "internal leakage: train_end is not before first test timestamp"
            raise ForecastInterfaceError(msg)
        model = factory()
        model.fit(train_index, train_y, frequency=spec.frequency, seed=spec.seed)
        yhat = np.asarray(model.predict(horizon=spec.horizon), dtype=float)
        lower, upper = model.predict_interval(horizon=spec.horizon, coverage=spec.coverage)
        lower = np.asarray(lower, dtype=float)
        upper = np.asarray(upper, dtype=float)
        if yhat.size != spec.horizon or lower.size != spec.horizon or upper.size != spec.horizon:
            msg = (
                f"forecast length mismatch: yhat={yhat.size}, lower={lower.size}, "
                f"upper={upper.size}, horizon={spec.horizon}"
            )
            raise ForecastInterfaceError(msg)
        metadata = model.metadata()
        metrics = _score_fold(
            actual=actual,
            yhat=yhat,
            lower=lower,
            upper=upper,
            insample=train_y,
            coverage=spec.coverage,
            seasonality_period=spec.seasonality_period,
        )
    except Exception as exc:
        return BacktestFoldResult(
            **base_kwargs,
            status="failed",
            actual=[float(v) for v in actual.tolist()],
            yhat=None,
            lower=None,
            upper=None,
            metrics=empty_metrics,
            metadata=None,
            error_type=type(exc).__name__,
            error_message=str(exc),
        )
    return BacktestFoldResult(
        **base_kwargs,
        status="completed",
        actual=[float(v) for v in actual.tolist()],
        yhat=[float(v) for v in yhat.tolist()],
        lower=[float(v) for v in lower.tolist()],
        upper=[float(v) for v in upper.tolist()],
        metrics=metrics,
        metadata=metadata,
        error_type=None,
        error_message=None,
    )


def _score_fold(
    *,
    actual: np.ndarray,
    yhat: np.ndarray,
    lower: np.ndarray,
    upper: np.ndarray,
    insample: np.ndarray,
    coverage: float,
    seasonality_period: int,
) -> FoldMetrics:
    return FoldMetrics(
        mae=_finite_or_none(mae(actual, yhat)),
        rmse=_finite_or_none(rmse(actual, yhat)),
        smape=_finite_or_none(smape(actual, yhat)),
        wmape=_finite_or_none(wmape(actual, yhat)),
        mase=_finite_or_none(mase(actual, yhat, insample, seasonality_period=seasonality_period)),
        wis=_finite_or_none(wis(actual, yhat, lower, upper, coverage=coverage)),
        interval_coverage=_finite_or_none(interval_coverage(actual, lower, upper)),
        interval_width=_finite_or_none(interval_width(lower, upper)),
    )


def _aggregate_folds(
    folds: Sequence[BacktestFoldResult],
    *,
    n_planned: int,
) -> BacktestAggregate:
    n_completed = sum(1 for fold in folds if fold.status == "completed")
    n_failed = sum(1 for fold in folds if fold.status == "failed")
    names = (
        "wis",
        "mae",
        "rmse",
        "smape",
        "wmape",
        "mase",
        "interval_coverage",
        "interval_width",
    )
    official: dict[str, float | None] = {}
    completed_only: dict[str, float | None] = {}
    for name in names:
        values = [getattr(fold.metrics, name) for fold in folds]
        official[name] = _mean_all_or_none(values)
        completed_only[name] = _mean_completed_only(values, folds)
    return BacktestAggregate(
        n_folds_planned=n_planned,
        n_folds_completed=n_completed,
        n_folds_failed=n_failed,
        wis=official["wis"],
        mae=official["mae"],
        rmse=official["rmse"],
        smape=official["smape"],
        wmape=official["wmape"],
        mase=official["mase"],
        interval_coverage=official["interval_coverage"],
        interval_width=official["interval_width"],
        wis_completed_only=completed_only["wis"],
        mae_completed_only=completed_only["mae"],
        rmse_completed_only=completed_only["rmse"],
        smape_completed_only=completed_only["smape"],
        wmape_completed_only=completed_only["wmape"],
        mase_completed_only=completed_only["mase"],
        interval_coverage_completed_only=completed_only["interval_coverage"],
        interval_width_completed_only=completed_only["interval_width"],
    )


def _mean_all_or_none(values: Sequence[float | None]) -> float | None:
    if not values:
        return None
    nums: list[float] = []
    for item in values:
        if item is None or not np.isfinite(item):
            return None
        nums.append(float(item))
    return float(np.mean(nums))


def _mean_completed_only(
    values: Sequence[float | None],
    folds: Sequence[BacktestFoldResult],
) -> float | None:
    nums: list[float] = []
    for item, fold in zip(values, folds, strict=True):
        if fold.status != "completed":
            continue
        if item is None or not np.isfinite(item):
            continue
        nums.append(float(item))
    if not nums:
        return None
    return float(np.mean(nums))


def _rank_by_official_wis(results: Sequence[ModelBacktestResult]) -> list[ModelRankingRow]:
    scored: list[tuple[float, str, int]] = []
    unranked: list[tuple[str, int]] = []
    for result in results:
        wis_value = result.aggregate.wis
        failed = result.aggregate.n_folds_failed
        if wis_value is None or not np.isfinite(wis_value):
            unranked.append((result.model_id, failed))
        else:
            scored.append((float(wis_value), result.model_id, failed))
    scored.sort(key=lambda row: (row[0], row[1]))
    unranked.sort(key=lambda row: row[0])
    ranking: list[ModelRankingRow] = []
    for rank, (wis_value, model_id, failed) in enumerate(scored, start=1):
        ranking.append(
            ModelRankingRow(
                rank=rank,
                model_id=model_id,
                official_wis=wis_value,
                n_folds_failed=failed,
            )
        )
    for model_id, failed in unranked:
        ranking.append(
            ModelRankingRow(
                rank=None,
                model_id=model_id,
                official_wis=None,
                n_folds_failed=failed,
            )
        )
    return ranking
