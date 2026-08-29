"""Compare baseline and agent evaluation artifacts. Improvement is computed, never hard-coded.

Usage (from the repository root):

    python evaluation/compare.py

Reads evaluation/results/baseline.json and evaluation/results/agent.json and
writes evaluation/results/comparison.json. Comparison is valid only when the
case lists are identical. Failed cases stay in the per-case record.
"""

# ruff: noqa: E402
# isort: skip_file

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from math import isfinite
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_serializer

_ROOT = Path(__file__).resolve().parents[1]
_BACKEND = _ROOT / "backend"
for _path in (_BACKEND, _ROOT):
    if str(_path) not in sys.path:
        sys.path.insert(0, str(_path))

from evaluation.cases.generators.catalog import REQUIRED_CASE_IDS
from evaluation.report import BaselineEvaluationResult, CaseEvaluation
from evaluation.run_baseline import git_commit

DEFAULT_BASELINE = _ROOT / "evaluation" / "results" / "baseline.json"
DEFAULT_AGENT = _ROOT / "evaluation" / "results" / "agent.json"
DEFAULT_OUTPUT = _ROOT / "evaluation" / "results" / "comparison.json"

JsonObject = dict[str, Any]
Direction = Literal["lower_is_better", "higher_is_better"]

LOWER_IS_BETTER = (
    "wis",
    "smape",
    "wmape",
    "mase",
    "mae",
    "rmse",
    "interval_width",
    "runtime_seconds",
    "n_cases_failed",
    "human_intervention_count",
    "wall_seconds",
)
HIGHER_IS_BETTER = ("interval_coverage",)
HOLD_OUT_METRICS = (
    "wis",
    "smape",
    "wmape",
    "mase",
    "interval_coverage",
    "interval_width",
)


class MetricComparison(BaseModel):
    """One metric compared from actual evaluation numbers. No hard-coded scores."""

    model_config = ConfigDict(extra="forbid")

    name: str
    direction: Direction
    baseline: float | None
    agent: float | None
    delta_agent_minus_baseline: float | None
    relative_improvement: float | None = Field(
        description=(
            "Positive means the agent is better for this metric's direction. "
            "(baseline-agent)/|baseline| if lower is better; "
            "(agent-baseline)/|baseline| if higher is better. None if undefined."
        )
    )


class CaseComparison(BaseModel):
    model_config = ConfigDict(extra="forbid")

    case_id: str
    baseline_status: str
    agent_status: str
    baseline_error_type: str | None
    agent_error_type: str | None
    baseline_error_message: str | None
    agent_error_message: str | None
    review_required: bool
    retry_number: int
    metrics: dict[str, MetricComparison]
    runtime_seconds: MetricComparison


class AggregateComparison(BaseModel):
    model_config = ConfigDict(extra="forbid")

    n_cases: int
    metrics: dict[str, MetricComparison]
    n_cases_failed: MetricComparison
    human_intervention_count: MetricComparison
    wall_seconds: MetricComparison
    cases_seconds: MetricComparison


class ComparisonResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    comparison_id: str
    timestamp: datetime
    git_commit: str | None
    baseline_evaluation_run_id: str
    agent_evaluation_run_id: str
    case_list: list[str]
    case_lists_identical: bool
    primary_metric: str = "wis"
    per_case: list[CaseComparison]
    aggregate: AggregateComparison
    errors: dict[str, list[dict[str, str | None]]]
    notes: list[str]

    @field_serializer("timestamp")
    def serialize_timestamp(self, value: datetime) -> str:
        aware = value if value.tzinfo is not None else value.replace(tzinfo=UTC)
        return aware.astimezone(UTC).isoformat().replace("+00:00", "Z")


class CaseListMismatchError(ValueError):
    """Baseline and agent were not scored on the same case list."""


def compare_metric(
    name: str,
    baseline: float | None,
    agent: float | None,
    *,
    direction: Direction,
) -> MetricComparison:
    delta: float | None = None
    relative: float | None = None
    if _finite(baseline) and _finite(agent):
        assert baseline is not None and agent is not None
        delta = float(agent) - float(baseline)
        if baseline != 0.0:
            if direction == "lower_is_better":
                relative = (float(baseline) - float(agent)) / abs(float(baseline))
            else:
                relative = (float(agent) - float(baseline)) / abs(float(baseline))
    return MetricComparison(
        name=name,
        direction=direction,
        baseline=baseline if _finite(baseline) else None,
        agent=agent if _finite(agent) else None,
        delta_agent_minus_baseline=delta,
        relative_improvement=relative,
    )


def compare_evaluations(
    baseline: BaselineEvaluationResult,
    agent: BaselineEvaluationResult,
    *,
    generated_at: datetime | None = None,
) -> ComparisonResult:
    if baseline.case_list != agent.case_list:
        msg = f"case_list mismatch: baseline={baseline.case_list!r} agent={agent.case_list!r}"
        raise CaseListMismatchError(msg)
    baseline_ids = [row.case_id for row in baseline.per_case]
    agent_ids = [row.case_id for row in agent.per_case]
    if baseline_ids != agent_ids:
        msg = f"per_case ids mismatch: baseline={baseline_ids!r} agent={agent_ids!r}"
        raise CaseListMismatchError(msg)
    created = generated_at if generated_at is not None else datetime.now(UTC)
    by_agent = {row.case_id: row for row in agent.per_case}
    per_case = [
        _compare_case(base_row, by_agent[base_row.case_id]) for base_row in baseline.per_case
    ]
    agg_metrics = {
        name: compare_metric(
            name,
            getattr(baseline.aggregate, name),
            getattr(agent.aggregate, name),
            direction=_direction(name),
        )
        for name in HOLD_OUT_METRICS
    }
    return ComparisonResult(
        comparison_id="comparison-" + created.strftime("%Y%m%dT%H%M%SZ"),
        timestamp=created,
        git_commit=git_commit(_ROOT),
        baseline_evaluation_run_id=baseline.evaluation_run_id,
        agent_evaluation_run_id=agent.evaluation_run_id,
        case_list=list(baseline.case_list),
        case_lists_identical=True,
        primary_metric="wis",
        per_case=per_case,
        aggregate=AggregateComparison(
            n_cases=len(baseline.case_list),
            metrics=agg_metrics,
            n_cases_failed=compare_metric(
                "n_cases_failed",
                float(baseline.aggregate.n_cases_failed),
                float(agent.aggregate.n_cases_failed),
                direction="lower_is_better",
            ),
            human_intervention_count=compare_metric(
                "human_intervention_count",
                float(baseline.aggregate.human_intervention_count),
                float(agent.aggregate.human_intervention_count),
                direction="lower_is_better",
            ),
            wall_seconds=compare_metric(
                "wall_seconds",
                _runtime(baseline, "wall_seconds"),
                _runtime(agent, "wall_seconds"),
                direction="lower_is_better",
            ),
            cases_seconds=compare_metric(
                "cases_seconds",
                _runtime(baseline, "cases_seconds"),
                _runtime(agent, "cases_seconds"),
                direction="lower_is_better",
            ),
        ),
        errors={"baseline": list(baseline.errors), "agent": list(agent.errors)},
        notes=[
            "relative_improvement is computed from the two evaluation JSON files.",
            "Official WIS uses the full case list; failures are not dropped.",
            "Positive relative_improvement means the agent is better for that metric.",
            f"Registered catalog case ids: {list(REQUIRED_CASE_IDS)}.",
        ],
    )


def run_comparison(
    *,
    baseline_path: Path | None = None,
    agent_path: Path | None = None,
    output_json: Path | None = None,
    generated_at: datetime | None = None,
) -> ComparisonResult:
    baseline = BaselineEvaluationResult.model_validate_json(
        (baseline_path if baseline_path is not None else DEFAULT_BASELINE).read_text(
            encoding="utf-8"
        )
    )
    agent = BaselineEvaluationResult.model_validate_json(
        (agent_path if agent_path is not None else DEFAULT_AGENT).read_text(encoding="utf-8")
    )
    result = compare_evaluations(baseline, agent, generated_at=generated_at)
    out = output_json if output_json is not None else DEFAULT_OUTPUT
    out.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(result.model_dump(mode="json"), indent=2, allow_nan=False) + "\n"
    with out.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(payload)
    return result


def _compare_case(baseline: CaseEvaluation, agent: CaseEvaluation) -> CaseComparison:
    metrics = {
        name: compare_metric(
            name,
            _holdout(baseline, name),
            _holdout(agent, name),
            direction=_direction(name),
        )
        for name in HOLD_OUT_METRICS
    }
    return CaseComparison(
        case_id=baseline.case_id,
        baseline_status=baseline.status,
        agent_status=agent.status,
        baseline_error_type=baseline.error_type,
        agent_error_type=agent.error_type,
        baseline_error_message=baseline.error_message,
        agent_error_message=agent.error_message,
        review_required=agent.review_required,
        retry_number=agent.retry_number,
        metrics=metrics,
        runtime_seconds=compare_metric(
            "runtime_seconds",
            baseline.runtime_seconds,
            agent.runtime_seconds,
            direction="lower_is_better",
        ),
    )


def _holdout(row: CaseEvaluation, name: str) -> float | None:
    scores = row.holdout_metrics
    if scores is None:
        return None
    value = getattr(scores, name)
    return value if _finite(value) else None


def _runtime(result: BaselineEvaluationResult, key: str) -> float | None:
    value = result.runtime.get(key)
    if isinstance(value, int | float):
        return float(value) if isfinite(float(value)) else None
    return None


def _direction(name: str) -> Direction:
    if name in HIGHER_IS_BETTER:
        return "higher_is_better"
    return "lower_is_better"


def _finite(value: float | None) -> bool:
    return value is not None and isfinite(float(value))


def main() -> int:
    parser = argparse.ArgumentParser(description="Compare ForecastWize baseline vs agent results.")
    parser.add_argument("--baseline", type=Path, default=DEFAULT_BASELINE)
    parser.add_argument("--agent", type=Path, default=DEFAULT_AGENT)
    parser.add_argument("--output-json", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    result = run_comparison(
        baseline_path=args.baseline,
        agent_path=args.agent,
        output_json=args.output_json,
    )
    print(f"wrote {args.output_json}")
    print(f"case_list={result.case_list}")
    print(f"case_lists_identical={result.case_lists_identical}")
    wis = result.aggregate.metrics["wis"]
    print(f"wis_baseline={wis.baseline}")
    print(f"wis_agent={wis.agent}")
    print(f"wis_relative_improvement={wis.relative_improvement}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
