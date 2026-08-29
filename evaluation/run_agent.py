"""Run the agentic evaluation on the shared case catalog.

Usage (from the repository root):

    python evaluation/run_agent.py

Loads **exactly** the same registered cases as run_baseline.py, runs
`run_orchestrator` on training rows only, scores the holdout with shared
forecasting metrics (WIS primary), and writes evaluation/results/agent.json.
No LLM. No hard-coded scores. Holdout values are not passed into the graph.
"""

# ruff: noqa: E402
# isort: skip_file

from __future__ import annotations

import argparse
import json
import sys
import time
import warnings
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd

_ROOT = Path(__file__).resolve().parents[1]
_BACKEND = _ROOT / "backend"
for _path in (_BACKEND, _ROOT):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from app.agents.orchestrator import run_orchestrator
from app.data.schemas import CONTEXT_COL, EVENT_COL, TIMESTAMP_COL, VALUE_COL
from app.data.validator import inspect_csv
from app.forecasting.base import ForecastInterfaceError, ForecastResult
from app.forecasting.missing_policy import LINEAR_INTERPOLATE_TRAIN, apply_linear_interpolate_train
from app.services.forecast_service import BASELINE_MODEL_IDS
from app.tools.verification_tools import ForecastSnapshot
from evaluation.cases.generators.catalog import DATA_DIR, CaseSpec, load_catalog
from evaluation.metrics import score_holdout
from evaluation.report import (
    BacktestModelSnapshot,
    BaselineEvaluationResult,
    CaseEvaluation,
    aggregate_cases,
    render_summary,
)
from evaluation.run_baseline import (
    COVERAGE,
    git_commit,
    mase_period,
    runtime_library_pins,
    seasonal_period_for,
    split_train_holdout,
)

DEFAULT_JSON = _ROOT / "evaluation" / "results" / "agent.json"
DEFAULT_MD = _ROOT / "evaluation" / "results" / "agent.md"


def run_agent_evaluation(
    *,
    output_json: Path | None = None,
    output_md: Path | None = None,
    candidate_model_ids: tuple[str, ...] | None = None,
    generated_at: datetime | None = None,
    data_dir: Path | None = None,
    persist_trajectory: bool = False,
) -> BaselineEvaluationResult:
    catalog = load_catalog()
    case_list = [case.case_id for case in catalog.cases]
    candidates = (
        tuple(candidate_model_ids) if candidate_model_ids is not None else BASELINE_MODEL_IDS
    )
    started = time.perf_counter()
    created = generated_at if generated_at is not None else datetime.now(UTC)
    run_id = "agent-" + created.strftime("%Y%m%dT%H%M%SZ")
    series_dir = data_dir if data_dir is not None else DATA_DIR
    per_case: list[CaseEvaluation] = []

    for case in catalog.cases:
        per_case.append(
            _evaluate_case(
                case,
                candidate_model_ids=candidates,
                series_dir=series_dir,
                generated_at=created,
                persist_trajectory=persist_trajectory,
                evaluation_run_id=run_id,
            )
        )

    result = BaselineEvaluationResult(
        evaluation_run_id=run_id,
        timestamp=created,
        git_commit=git_commit(_ROOT),
        system="agent",
        catalog_id=catalog.catalog_id,
        catalog_version=catalog.catalog_version,
        case_list=case_list,
        configuration={
            "workflow": "run_orchestrator",
            "coverage": COVERAGE,
            "holdout_passed_to_graph": False,
            "train_missing_policy": LINEAR_INTERPOLATE_TRAIN,
            **runtime_library_pins(),
        },
        model_configuration={
            "candidate_model_ids": ",".join(candidates),
            "selection": "orchestrator_backtest_wis_then_verify",
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
    candidate_model_ids: tuple[str, ...],
    series_dir: Path,
    generated_at: datetime,
    persist_trajectory: bool,
    evaluation_run_id: str,
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
        event_labels = _train_optional_column(frame, EVENT_COL, case.history_length)
        context_labels = _train_optional_column(frame, CONTEXT_COL, case.history_length)
        period = seasonal_period_for(case)
        state = run_orchestrator(
            train_ts,
            train_y,
            horizon=case.forecast_horizon,
            frequency=case.frequency,
            event_labels=event_labels,
            context_labels=context_labels,
            candidate_model_ids=candidate_model_ids,
            seasonal_period=period,
            seed=case.random_seed,
            coverage=COVERAGE,
            run_id=f"{evaluation_run_id}-{case.case_id}",
            generated_at=generated_at,
            persist_trajectory=persist_trajectory,
        )
        forecast = state.forecast
        if forecast is None:
            msg = state.error_message or "orchestrator produced no forecast"
            raise ForecastInterfaceError(msg)
        yhat, lower, upper = _forecast_arrays(forecast)
        if not (np.isfinite(yhat).all() and np.isfinite(lower).all() and np.isfinite(upper).all()):
            msg = "agent forecast produced non-finite yhat or interval values"
            raise ForecastInterfaceError(msg)
        scores = score_holdout(
            test_y,
            yhat,
            lower,
            upper,
            train_y,
            coverage=COVERAGE,
            seasonality_period=mase_period(case),
        )
        review_required = _review_required(state)
        selected = state.selected_strategy_id
        rule = None
        snapshots: list[BacktestModelSnapshot] = []
        if state.strategist_report is not None:
            rule = state.strategist_report.selection_rule
            snapshots = [
                BacktestModelSnapshot(
                    model_id=row.model_id,
                    official_wis=row.official_wis,
                    wis_completed_only=row.wis_completed_only,
                    n_folds_planned=row.n_folds_planned,
                    n_folds_completed=row.n_folds_completed,
                    n_folds_failed=row.n_folds_failed,
                    rank=row.rank,
                )
                for row in state.strategist_report.comparison
            ]
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
            yhat=list(yhat),
            lower=list(lower),
            upper=list(upper),
            runtime_seconds=time.perf_counter() - t0,
            review_required=review_required,
            retry_number=state.retry_number,
            verification_overall=state.verification_overall,
            human_checkpoint_status=(
                None if state.human_checkpoint is None else state.human_checkpoint.status
            ),
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
            review_required=False,
            retry_number=0,
            verification_overall=None,
            human_checkpoint_status=None,
        )


def _train_optional_column(
    frame: pd.DataFrame,
    column: str,
    history_length: int,
) -> pd.Series | None:
    if column not in frame.columns:
        return None
    return frame[column].iloc[:history_length]


def _forecast_arrays(
    forecast: ForecastResult | ForecastSnapshot,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    return (
        np.asarray(forecast.yhat, dtype=float),
        np.asarray(forecast.lower, dtype=float),
        np.asarray(forecast.upper, dtype=float),
    )


def _review_required(state: object) -> bool:
    review = bool(getattr(state, "review_required", False))
    status = getattr(state, "status", None)
    checkpoint = getattr(state, "human_checkpoint", None)
    required = bool(getattr(checkpoint, "required", False)) if checkpoint is not None else False
    waiting = getattr(checkpoint, "status", None) == "waiting_for_approval"
    return review or required or waiting or status == "waiting_for_approval"


def main() -> int:
    parser = argparse.ArgumentParser(description="Run ForecastWize agent evaluation.")
    parser.add_argument("--output-json", type=Path, default=DEFAULT_JSON)
    parser.add_argument("--output-md", type=Path, default=DEFAULT_MD)
    args = parser.parse_args()
    warnings.filterwarnings("ignore", category=UserWarning)
    result = run_agent_evaluation(output_json=args.output_json, output_md=args.output_md)
    print(f"wrote {args.output_json}")
    print(f"wrote {args.output_md}")
    print(f"case_list={result.case_list}")
    print(f"official_wis={result.aggregate.wis}")
    print(f"n_failed={result.aggregate.n_cases_failed}")
    print(f"human_intervention_count={result.aggregate.human_intervention_count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
