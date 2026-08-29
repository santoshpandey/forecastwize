from __future__ import annotations

import inspect
from datetime import UTC, datetime

import pytest
from evaluation.compare import (
    CaseListMismatchError,
    compare_evaluations,
    compare_metric,
)
from evaluation.metrics import score_holdout
from evaluation.report import (
    BaselineEvaluationResult,
    CaseEvaluation,
    aggregate_cases,
)


def _scores(*, wis: float) -> object:
    return score_holdout(
        [1.0, 1.0],
        [1.0, 1.0],
        [0.0, 0.0],
        [2.0, 2.0],
        [1.0, 1.0, 1.0],
        coverage=0.95,
        seasonality_period=1,
    ).model_copy(update={"wis": wis, "smape": wis * 2, "wmape": wis * 2, "mase": wis})


def _case(case_id: str, *, wis: float | None, status: str = "completed", review: bool = False):
    metrics = None if wis is None else _scores(wis=wis)
    return CaseEvaluation(
        case_id=case_id,
        status=status,
        selected_model_id=None if status == "failed" else "naive",
        selection_rule=None if status == "failed" else "official_backtest_wis",
        n_train=10,
        forecast_horizon=2,
        frequency="D",
        random_seed=1,
        holdout_metrics=metrics,
        backtest=[],
        error_type=None if status != "failed" else "RuntimeError",
        error_message=None if status != "failed" else "boom",
        runtime_seconds=1.0 if case_id == "001" else 2.0,
        review_required=review,
        retry_number=1 if review else 0,
    )


def _result(system: str, cases: list[CaseEvaluation]) -> BaselineEvaluationResult:
    return BaselineEvaluationResult(
        evaluation_run_id=f"{system}-test",
        timestamp=datetime(2021, 6, 1, tzinfo=UTC),
        git_commit=None,
        system=system,
        catalog_id="forecastwize-eval-v1",
        catalog_version=1,
        case_list=[row.case_id for row in cases],
        configuration={},
        model_configuration={},
        per_case=cases,
        aggregate=aggregate_cases(cases),
        errors=[
            {
                "case_id": row.case_id,
                "error_type": row.error_type,
                "error_message": row.error_message,
            }
            for row in cases
            if row.status == "failed"
        ],
        runtime={"wall_seconds": 10.0 if system == "baseline" else 12.0, "cases_seconds": 3.0},
    )


def test_compare_source_does_not_hardcode_improvement() -> None:
    from evaluation import compare

    text = inspect.getsource(compare).lower()
    assert "import fastapi" not in text
    assert "relative_improvement=0.18" not in text
    assert "-18%" not in text
    assert '"wis": 1.2' not in text
    assert "langgraph" not in text


def test_relative_improvement_is_computed_from_inputs() -> None:
    lower = compare_metric("wis", 10.0, 8.0, direction="lower_is_better")
    assert lower.delta_agent_minus_baseline == -2.0
    assert lower.relative_improvement == pytest.approx(0.2)
    higher = compare_metric("interval_coverage", 0.5, 0.8, direction="higher_is_better")
    assert higher.relative_improvement == pytest.approx(0.6)
    missing = compare_metric("wis", 1.0, None, direction="lower_is_better")
    assert missing.relative_improvement is None
    zero = compare_metric("wis", 0.0, 1.0, direction="lower_is_better")
    assert zero.delta_agent_minus_baseline == 1.0
    assert zero.relative_improvement is None


def test_comparison_keeps_failed_cases_and_requires_identical_lists() -> None:
    baseline = _result(
        "baseline",
        [_case("001", wis=4.0), _case("002", wis=None, status="failed")],
    )
    agent = _result(
        "agent",
        [_case("001", wis=3.0, review=True), _case("002", wis=None, status="failed")],
    )
    compared = compare_evaluations(baseline, agent, generated_at=datetime(2021, 6, 2, tzinfo=UTC))
    assert compared.case_lists_identical is True
    assert [row.case_id for row in compared.per_case] == ["001", "002"]
    wis = compared.aggregate.metrics["wis"]
    assert wis.baseline is None
    assert wis.agent is None
    case_one = compared.per_case[0].metrics["wis"]
    assert case_one.baseline == 4.0
    assert case_one.agent == 3.0
    assert case_one.relative_improvement == pytest.approx(0.25)
    failed_row = compared.per_case[1]
    assert failed_row.baseline_status == "failed"
    assert failed_row.agent_status == "failed"
    assert failed_row.baseline_error_type == "RuntimeError"
    assert compared.errors["baseline"][0]["case_id"] == "002"
    assert compared.aggregate.human_intervention_count.agent == 1.0
    assert compared.aggregate.n_cases_failed.baseline == 1.0
    mismatched = _result("agent", [_case("001", wis=3.0), _case("003", wis=1.0)])
    with pytest.raises(CaseListMismatchError, match="case_list mismatch"):
        compare_evaluations(baseline, mismatched)
