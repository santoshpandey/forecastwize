"""Typed evaluation records and a human-readable baseline summary. No FastAPI/LLM."""

from __future__ import annotations

from datetime import UTC, datetime
from math import isfinite

from pydantic import BaseModel, ConfigDict, Field, field_serializer

from evaluation.metrics import HoldoutScores, completed_only_mean, official_mean


def _to_utc_iso(value: datetime) -> str:
    aware = value if value.tzinfo is not None else value.replace(tzinfo=UTC)
    return aware.astimezone(UTC).isoformat().replace("+00:00", "Z")


class BacktestModelSnapshot(BaseModel):
    model_config = ConfigDict(extra="forbid")

    model_id: str
    official_wis: float | None
    wis_completed_only: float | None
    n_folds_planned: int
    n_folds_completed: int
    n_folds_failed: int
    rank: int | None


class CaseEvaluation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    case_id: str
    status: str
    selected_model_id: str | None
    selection_rule: str | None
    n_train: int
    forecast_horizon: int
    frequency: str
    random_seed: int
    holdout_metrics: HoldoutScores | None
    backtest: list[BacktestModelSnapshot]
    yhat: list[float] | None = None
    lower: list[float] | None = None
    upper: list[float] | None = None
    error_type: str | None = None
    error_message: str | None = None
    runtime_seconds: float
    review_required: bool = False
    retry_number: int = 0
    verification_overall: str | None = None
    human_checkpoint_status: str | None = None


class AggregateMetrics(BaseModel):
    """Official means include every registered case. Failures are not dropped."""

    model_config = ConfigDict(extra="forbid")

    n_cases: int
    n_cases_completed: int
    n_cases_failed: int
    wis: float | None = Field(description="Official mean WIS over the full case list.")
    smape: float | None
    wmape: float | None
    mase: float | None
    mae: float | None
    rmse: float | None
    interval_coverage: float | None
    interval_width: float | None
    wis_completed_only: float | None
    smape_completed_only: float | None
    wmape_completed_only: float | None
    mase_completed_only: float | None
    mae_completed_only: float | None
    rmse_completed_only: float | None
    interval_coverage_completed_only: float | None
    interval_width_completed_only: float | None
    human_intervention_count: int = 0
    cost: float | None = None


class BaselineEvaluationResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    evaluation_run_id: str
    timestamp: datetime
    git_commit: str | None
    system: str
    catalog_id: str
    catalog_version: int
    case_list: list[str]
    configuration: dict[str, str | int | float | bool | None]
    model_configuration: dict[str, str | int | float | bool | None]
    per_case: list[CaseEvaluation]
    aggregate: AggregateMetrics
    errors: list[dict[str, str | None]]
    runtime: dict[str, float | None]

    @field_serializer("timestamp")
    def serialize_timestamp(self, value: datetime) -> str:
        return _to_utc_iso(value)


def aggregate_cases(per_case: list[CaseEvaluation]) -> AggregateMetrics:
    n_failed = sum(1 for row in per_case if row.status != "completed")
    n_completed = sum(1 for row in per_case if row.status == "completed")
    names = (
        "wis",
        "smape",
        "wmape",
        "mase",
        "mae",
        "rmse",
        "interval_coverage",
        "interval_width",
    )
    by_name: dict[str, list[float | None]] = {name: [] for name in names}
    for row in per_case:
        scores = row.holdout_metrics
        for name in names:
            value = None if scores is None else getattr(scores, name)
            by_name[name].append(value)
    return AggregateMetrics(
        n_cases=len(per_case),
        n_cases_completed=n_completed,
        n_cases_failed=n_failed,
        wis=official_mean(by_name["wis"]),
        smape=official_mean(by_name["smape"]),
        wmape=official_mean(by_name["wmape"]),
        mase=official_mean(by_name["mase"]),
        mae=official_mean(by_name["mae"]),
        rmse=official_mean(by_name["rmse"]),
        interval_coverage=official_mean(by_name["interval_coverage"]),
        interval_width=official_mean(by_name["interval_width"]),
        wis_completed_only=completed_only_mean(by_name["wis"]),
        smape_completed_only=completed_only_mean(by_name["smape"]),
        wmape_completed_only=completed_only_mean(by_name["wmape"]),
        mase_completed_only=completed_only_mean(by_name["mase"]),
        mae_completed_only=completed_only_mean(by_name["mae"]),
        rmse_completed_only=completed_only_mean(by_name["rmse"]),
        interval_coverage_completed_only=completed_only_mean(by_name["interval_coverage"]),
        interval_width_completed_only=completed_only_mean(by_name["interval_width"]),
        human_intervention_count=sum(1 for row in per_case if row.review_required),
        cost=None,
    )


def render_summary(result: BaselineEvaluationResult) -> str:
    title = (
        "ForecastWize baseline evaluation"
        if result.system == "baseline"
        else f"ForecastWize {result.system} evaluation"
    )
    lines = [
        f"# {title}",
        "",
        f"- evaluation_run_id: `{result.evaluation_run_id}`",
        f"- timestamp: `{_to_utc_iso(result.timestamp)}`",
        f"- git_commit: `{result.git_commit or 'unavailable'}`",
        f"- system: `{result.system}`",
        f"- catalog: `{result.catalog_id}` v{result.catalog_version}",
        f"- case_list: {', '.join(result.case_list)}",
        f"- wall_seconds: {result.runtime.get('wall_seconds')}",
        "",
        "## Aggregate",
        "",
        "Official means include **every** registered case. Failed cases are not dropped.",
        "`*_completed_only` is labeled and is **not** the headline result.",
        "",
        f"- cases completed/failed: {result.aggregate.n_cases_completed}/"
        f"{result.aggregate.n_cases_failed} of {result.aggregate.n_cases}",
        f"- official WIS (headline): {_fmt(result.aggregate.wis)}",
        f"- WIS completed-only (not headline): {_fmt(result.aggregate.wis_completed_only)}",
        f"- official sMAPE: {_fmt(result.aggregate.smape)}",
        f"- official WMAPE: {_fmt(result.aggregate.wmape)}",
        f"- official MASE: {_fmt(result.aggregate.mase)}",
        f"- official coverage: {_fmt(result.aggregate.interval_coverage)}",
        f"- official interval width: {_fmt(result.aggregate.interval_width)}",
        f"- human_intervention_count: {result.aggregate.human_intervention_count}",
        f"- cost: {_fmt(result.aggregate.cost)}",
        "",
        "## Per case",
        "",
        "| case_id | status | model | WIS | sMAPE | seconds | error |",
        "|---|---|---|---|---|---|---|",
    ]
    for row in result.per_case:
        wis = None if row.holdout_metrics is None else row.holdout_metrics.wis
        smape = None if row.holdout_metrics is None else row.holdout_metrics.smape
        err = (row.error_message or "").replace("|", "/")
        if len(err) > 80:
            err = err[:77] + "..."
        lines.append(
            f"| {row.case_id} | {row.status} | {row.selected_model_id or ''} | "
            f"{_fmt(wis)} | {_fmt(smape)} | {row.runtime_seconds:.3f} | {err} |"
        )
    lines.extend(["", "## Errors", ""])
    if not result.errors:
        lines.append("None.")
    else:
        for item in result.errors:
            lines.append(
                f"- {item.get('case_id')}: {item.get('error_type')}: {item.get('error_message')}"
            )
    lines.extend(
        [
            "",
            "These numbers come from the executable harness, not from hand-edited tables.",
            "Do not treat remembered percentages as the source of truth.",
            "",
        ]
    )
    return "\n".join(lines)


def _fmt(value: float | None) -> str:
    if value is None:
        return "—"
    if isinstance(value, float) and not isfinite(value):
        return "—"
    return f"{value:.6g}"
