"""Run the conventional baseline evaluation on the shared case catalog.

Usage (from the repository root):

    python evaluation/run_baseline.py

Loads every registered case, backtests candidate models on training data only,
fits the selected model, scores the holdout with shared forecasting metrics
(WIS primary), and writes evaluation/results/baseline.json. No LLM. No
hard-coded scores.
"""

# ruff: noqa: E402
# isort: skip_file

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from datetime import UTC, datetime
from importlib import metadata
from pathlib import Path

import numpy as np
import pandas as pd

_ROOT = Path(__file__).resolve().parents[1]
_BACKEND = _ROOT / "backend"
for _path in (_BACKEND, _ROOT):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from app.data.schemas import TIMESTAMP_COL, VALUE_COL
from app.data.seasonality import period_from_frequency
from app.data.validator import inspect_csv
from app.forecasting.backtesting import BacktestSpec, run_rolling_origin_backtest
from app.forecasting.base import ForecastInterfaceError
from app.forecasting.missing_policy import LINEAR_INTERPOLATE_TRAIN, apply_linear_interpolate_train
from app.services.forecast_service import (
    BASELINE_MODEL_IDS,
    create_baseline_model,
    run_baseline_forecast,
)
from evaluation.cases.generators.catalog import DATA_DIR, CaseSpec, load_catalog
from evaluation.metrics import score_holdout
from evaluation.report import (
    BacktestModelSnapshot,
    BaselineEvaluationResult,
    CaseEvaluation,
    aggregate_cases,
    render_summary,
)

DEFAULT_JSON = _ROOT / "evaluation" / "results" / "baseline.json"
DEFAULT_MD = _ROOT / "evaluation" / "results" / "baseline.md"
FALLBACK_MODEL_ORDER = ("naive", "seasonal_naive", "ets", "arima")
COVERAGE = 0.95
TARGET_BACKTEST_FOLDS = 5


def git_commit(repo: Path) -> str | None:
    try:
        completed = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=repo,
            check=True,
            capture_output=True,
            text=True,
            timeout=15,
        )
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return None
    value = completed.stdout.strip()
    return value or None


def package_version(name: str) -> str | None:
    try:
        return metadata.version(name)
    except metadata.PackageNotFoundError:
        return None


def runtime_library_pins() -> dict[str, str | None]:
    """Installed library versions for a run. Pins live in backend/requirements.txt."""
    return {
        "python": sys.version.split()[0],
        "pandas": package_version("pandas"),
        "numpy": package_version("numpy"),
        "scipy": package_version("scipy"),
        "statsmodels": package_version("statsmodels"),
        "pyyaml": package_version("PyYAML") or package_version("pyyaml"),
        "pins_file": "backend/requirements.txt",
        "catalog_registry": "evaluation/cases/case_registry.yaml",
    }


def seasonal_period_for(case: CaseSpec) -> int | None:
    if case.generation.seasonal_period is not None:
        return int(case.generation.seasonal_period)
    return period_from_frequency(case.frequency)


def mase_period(case: CaseSpec) -> int:
    period = seasonal_period_for(case)
    if period is None or period < 1:
        return 1
    return period


def backtest_min_train_size(n_train: int, horizon: int, period: int | None) -> int | None:
    max_allowed = n_train - horizon
    if max_allowed < 1:
        return None
    needed = 8
    if period is not None:
        needed = max(needed, int(period))
    return min(needed, max_allowed)


def backtest_step(n_train: int, horizon: int, min_train_size: int) -> int:
    last = n_train - 1 - horizon
    first = min_train_size - 1
    if first > last:
        return 1
    n_possible = last - first + 1
    return max(1, (n_possible + TARGET_BACKTEST_FOLDS - 1) // TARGET_BACKTEST_FOLDS)


def split_train_holdout(
    timestamps: pd.Series | pd.DatetimeIndex,
    values: pd.Series | np.ndarray,
    *,
    history_length: int,
    forecast_horizon: int,
) -> tuple[pd.Series, np.ndarray, pd.Series, np.ndarray]:
    ts = pd.Series(timestamps)
    y = np.asarray(values, dtype=float)
    expected = history_length + forecast_horizon
    if y.size != expected:
        msg = f"series length {y.size} != history_length+horizon {expected}"
        raise ForecastInterfaceError(msg)
    train_ts = ts.iloc[:history_length]
    test_ts = ts.iloc[history_length:]
    train_y = y[:history_length]
    test_y = y[history_length:]
    return train_ts, train_y, test_ts, test_y


def select_model_id(snapshots: list[BacktestModelSnapshot]) -> tuple[str | None, str]:
    ranked = [row for row in snapshots if row.rank is not None]
    ranked.sort(key=lambda row: (row.rank if row.rank is not None else 10**9, row.model_id))
    if ranked:
        return ranked[0].model_id, "official_backtest_wis"
    completed = [
        (row.wis_completed_only, row.model_id)
        for row in snapshots
        if row.wis_completed_only is not None and row.n_folds_completed > 0
    ]
    if completed:
        completed.sort(key=lambda item: (item[0], item[1]))
        return completed[0][1], "completed_only_backtest_wis"
    return None, "no_backtest_winner"


def run_baseline_evaluation(
    *,
    output_json: Path | None = None,
    output_md: Path | None = None,
    model_ids: tuple[str, ...] | None = None,
    generated_at: datetime | None = None,
    data_dir: Path | None = None,
) -> BaselineEvaluationResult:
    catalog = load_catalog()
    case_list = [case.case_id for case in catalog.cases]
    candidates = tuple(model_ids) if model_ids is not None else BASELINE_MODEL_IDS
    started = time.perf_counter()
    created = generated_at if generated_at is not None else datetime.now(UTC)
    run_id = "baseline-" + created.strftime("%Y%m%dT%H%M%SZ")
    series_dir = data_dir if data_dir is not None else DATA_DIR
    per_case: list[CaseEvaluation] = []

    for case in catalog.cases:
        per_case.append(
            _evaluate_case(
                case,
                model_ids=candidates,
                series_dir=series_dir,
                generated_at=created,
            )
        )

    result = BaselineEvaluationResult(
        evaluation_run_id=run_id,
        timestamp=created,
        git_commit=git_commit(_ROOT),
        system="baseline",
        catalog_id=catalog.catalog_id,
        catalog_version=catalog.catalog_version,
        case_list=case_list,
        configuration={
            "window_type": "expanding",
            "coverage": COVERAGE,
            "target_backtest_folds": TARGET_BACKTEST_FOLDS,
            "selection": "backtest_wis_then_fallback_order",
            "train_missing_policy": LINEAR_INTERPOLATE_TRAIN,
            **runtime_library_pins(),
        },
        model_configuration={
            "candidate_model_ids": ",".join(candidates),
            "fallback_order": ",".join(FALLBACK_MODEL_ORDER),
        },
        per_case=per_case,
        aggregate=aggregate_cases(per_case),
        errors=[
            {
                "case_id": row.case_id,
                "error_type": row.error_type,
                "error_message": row.error_message,
            }
            for row in per_case
            if row.status == "failed"
        ],
        runtime={
            "wall_seconds": time.perf_counter() - started,
            "cases_seconds": sum(row.runtime_seconds for row in per_case),
        },
    )
    json_path = output_json if output_json is not None else DEFAULT_JSON
    md_path = output_md if output_md is not None else DEFAULT_MD
    json_path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(result.model_dump(mode="json"), indent=2, allow_nan=False) + "\n"
    with json_path.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(payload)
    with md_path.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(render_summary(result))
    return result


def _evaluate_case(
    case: CaseSpec,
    *,
    model_ids: tuple[str, ...],
    series_dir: Path,
    generated_at: datetime,
) -> CaseEvaluation:
    t0 = time.perf_counter()
    path = series_dir / case.csv_filename
    try:
        inspection = inspect_csv(path)
        if not inspection.is_valid():
            messages = "; ".join(item.message for item in inspection.error_issues())
            raise ForecastInterfaceError(messages)
        frame = inspection.derived
        timestamps = frame[TIMESTAMP_COL]
        values = frame[VALUE_COL].to_numpy(dtype=float)
        train_ts, train_y, _test_ts, test_y = split_train_holdout(
            timestamps,
            values,
            history_length=case.history_length,
            forecast_horizon=case.forecast_horizon,
        )
        train_y, _policy = apply_linear_interpolate_train(train_ts, train_y)
        period = seasonal_period_for(case)
        snapshots, selected, rule = _backtest_and_select(
            case,
            train_ts=train_ts,
            train_y=train_y,
            model_ids=model_ids,
            period=period,
            generated_at=generated_at,
        )
        if selected is None:
            selected, rule = _fallback_fit(
                case,
                train_ts=train_ts,
                train_y=train_y,
                generated_at=generated_at,
            )
        try:
            forecast = run_baseline_forecast(
                train_ts,
                train_y,
                frequency=case.frequency,
                horizon=case.forecast_horizon,
                model_id=selected,
                coverage=COVERAGE,
                seed=case.random_seed,
                seasonal_period=period,
                generated_at=generated_at,
            )
        except (ForecastInterfaceError, ValueError, np.linalg.LinAlgError, RuntimeError):
            selected, rule = _fallback_fit(
                case,
                train_ts=train_ts,
                train_y=train_y,
                generated_at=generated_at,
            )
            forecast = run_baseline_forecast(
                train_ts,
                train_y,
                frequency=case.frequency,
                horizon=case.forecast_horizon,
                model_id=selected,
                coverage=COVERAGE,
                seed=case.random_seed,
                seasonal_period=period,
                generated_at=generated_at,
            )
        if not (
            np.isfinite(forecast.yhat).all()
            and np.isfinite(forecast.lower).all()
            and np.isfinite(forecast.upper).all()
        ):
            msg = "baseline forecast produced non-finite yhat or interval values"
            raise ForecastInterfaceError(msg)
        scores = score_holdout(
            test_y,
            forecast.yhat,
            forecast.lower,
            forecast.upper,
            train_y,
            coverage=COVERAGE,
            seasonality_period=mase_period(case),
        )
        return CaseEvaluation(
            case_id=case.case_id,
            status="completed",
            selected_model_id=selected,
            selection_rule=rule,
            n_train=case.history_length,
            forecast_horizon=case.forecast_horizon,
            frequency=case.frequency,
            random_seed=case.random_seed,
            holdout_metrics=scores,
            backtest=snapshots,
            yhat=list(forecast.yhat),
            lower=list(forecast.lower),
            upper=list(forecast.upper),
            runtime_seconds=time.perf_counter() - t0,
        )
    except Exception as exc:
        return CaseEvaluation(
            case_id=case.case_id,
            status="failed",
            selected_model_id=None,
            selection_rule=None,
            n_train=case.history_length,
            forecast_horizon=case.forecast_horizon,
            frequency=case.frequency,
            random_seed=case.random_seed,
            holdout_metrics=None,
            backtest=[],
            error_type=type(exc).__name__,
            error_message=str(exc),
            runtime_seconds=time.perf_counter() - t0,
        )


def _backtest_and_select(
    case: CaseSpec,
    *,
    train_ts: object,
    train_y: object,
    model_ids: tuple[str, ...],
    period: int | None,
    generated_at: datetime,
) -> tuple[list[BacktestModelSnapshot], str | None, str]:
    n_train = case.history_length
    horizon = case.forecast_horizon
    min_train = backtest_min_train_size(n_train, horizon, period)
    if min_train is None:
        return [], None, "no_backtest_winner"
    step = backtest_step(n_train, horizon, min_train)
    spec = BacktestSpec(
        frequency=case.frequency,
        horizon=horizon,
        min_train_size=min_train,
        window_type="expanding",
        step=step,
        coverage=COVERAGE,
        seed=case.random_seed,
        seasonality_period=mase_period(case),
    )
    factories = [(model_id, _factory(model_id, period)) for model_id in model_ids]
    try:
        comparison = run_rolling_origin_backtest(
            train_ts,
            train_y,
            factories,
            spec,
            generated_at=generated_at,
        )
    except ForecastInterfaceError:
        return [], None, "no_backtest_winner"
    rank_by_id = {row.model_id: row.rank for row in comparison.ranking}
    snapshots = [
        BacktestModelSnapshot(
            model_id=row.model_id,
            official_wis=row.aggregate.wis,
            wis_completed_only=row.aggregate.wis_completed_only,
            n_folds_planned=row.aggregate.n_folds_planned,
            n_folds_completed=row.aggregate.n_folds_completed,
            n_folds_failed=row.aggregate.n_folds_failed,
            rank=rank_by_id.get(row.model_id),
        )
        for row in comparison.results
    ]
    selected, rule = select_model_id(snapshots)
    return snapshots, selected, rule


def _fallback_fit(
    case: CaseSpec,
    *,
    train_ts: object,
    train_y: object,
    generated_at: datetime,
) -> tuple[str, str]:
    period = seasonal_period_for(case)
    last_error: Exception | None = None
    for model_id in FALLBACK_MODEL_ORDER:
        try:
            run_baseline_forecast(
                train_ts,
                train_y,
                frequency=case.frequency,
                horizon=case.forecast_horizon,
                model_id=model_id,
                coverage=COVERAGE,
                seed=case.random_seed,
                seasonal_period=period,
                generated_at=generated_at,
            )
            return model_id, "fallback_order_first_successful_fit"
        except Exception as exc:
            last_error = exc
    msg = f"all fallback models failed: {last_error}"
    raise ForecastInterfaceError(msg)


def _factory(model_id: str, seasonal_period: int | None):
    def _make():
        return create_baseline_model(model_id, seasonal_period=seasonal_period)

    return _make


def main() -> int:
    parser = argparse.ArgumentParser(description="Run ForecastWize baseline evaluation.")
    parser.add_argument("--output-json", type=Path, default=DEFAULT_JSON)
    parser.add_argument("--output-md", type=Path, default=DEFAULT_MD)
    args = parser.parse_args()
    import warnings

    warnings.filterwarnings("ignore", category=UserWarning)
    result = run_baseline_evaluation(output_json=args.output_json, output_md=args.output_md)
    print(f"wrote {args.output_json}")
    print(f"wrote {args.output_md}")
    print(f"case_list={result.case_list}")
    print(f"official_wis={result.aggregate.wis}")
    print(f"n_failed={result.aggregate.n_cases_failed}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
