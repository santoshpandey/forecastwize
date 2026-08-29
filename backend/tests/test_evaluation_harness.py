from __future__ import annotations

import inspect
import json
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
from app.forecasting.metrics import wis as forecasting_wis
from evaluation.cases.generators import REQUIRED_CASE_IDS, load_catalog
from evaluation.compare import compare_evaluations
from evaluation.metrics import completed_only_mean, official_mean, score_holdout
from evaluation.report import (
    BaselineEvaluationResult,
    CaseEvaluation,
    aggregate_cases,
    render_summary,
)
from evaluation.run_agent import run_agent_evaluation
from evaluation.run_baseline import (
    backtest_min_train_size,
    git_commit,
    run_baseline_evaluation,
    runtime_library_pins,
    split_train_holdout,
)


def test_metrics_invoke_forecasting_and_do_not_fork_wis_formula() -> None:
    import evaluation.metrics as metrics_mod

    text = inspect.getsource(metrics_mod)
    assert "from app.forecasting.metrics import" in text
    assert "1.0 / (k + 0.5)" not in text
    assert "import fastapi" not in text.lower()
    actual = np.array([1.0, 2.0])
    yhat = np.array([1.0, 3.0])
    lower = np.array([0.0, 1.0])
    upper = np.array([2.0, 4.0])
    scores = score_holdout(
        actual, yhat, lower, upper, np.array([1.0, 1.5, 2.0]), coverage=0.9, seasonality_period=1
    )
    assert scores.wis == forecasting_wis(actual, yhat, lower, upper, coverage=0.9)


def test_official_mean_keeps_failures() -> None:
    assert official_mean([1.0, 3.0]) == 2.0
    assert official_mean([1.0, None]) is None
    assert completed_only_mean([1.0, None, 3.0]) == 2.0


def test_split_is_time_aware_and_uses_history_then_holdout() -> None:
    import pandas as pd

    stamps = pd.Series(pd.date_range("2020-01-01", periods=10, freq="D", tz="UTC"))
    values = np.arange(10, dtype=float)
    train_ts, train_y, test_ts, test_y = split_train_holdout(
        stamps, values, history_length=7, forecast_horizon=3
    )
    assert len(train_y) == 7
    assert len(test_y) == 3
    np.testing.assert_array_equal(train_y, values[:7])
    np.testing.assert_array_equal(test_y, values[7:])
    assert train_ts.iloc[-1] < test_ts.iloc[0]


def test_harness_source_has_no_hardcoded_scores() -> None:
    from evaluation import compare, report, run_agent, run_baseline

    for module in (run_baseline, run_agent, report, compare):
        text = inspect.getsource(module).lower()
        assert "import fastapi" not in text
        assert "wis = 0." not in text
        assert '"wis": 1' not in text
        assert "improvement = 0." not in text
        assert "langgraph" not in text


def test_aggregate_does_not_drop_failed_cases() -> None:
    completed = CaseEvaluation(
        case_id="001",
        status="completed",
        selected_model_id="naive",
        selection_rule="x",
        n_train=10,
        forecast_horizon=2,
        frequency="D",
        random_seed=1,
        holdout_metrics=score_holdout(
            [1.0, 1.0],
            [1.0, 1.0],
            [0.0, 0.0],
            [2.0, 2.0],
            [1.0, 1.0, 1.0],
            coverage=0.95,
            seasonality_period=1,
        ),
        backtest=[],
        runtime_seconds=0.01,
    )
    failed = CaseEvaluation(
        case_id="002",
        status="failed",
        selected_model_id=None,
        selection_rule=None,
        n_train=10,
        forecast_horizon=2,
        frequency="D",
        random_seed=1,
        holdout_metrics=None,
        backtest=[],
        error_type="RuntimeError",
        error_message="boom",
        runtime_seconds=0.01,
    )
    agg = aggregate_cases([completed, failed])
    assert agg.n_cases == 2
    assert agg.n_cases_failed == 1
    assert agg.wis is None
    assert agg.wis_completed_only is not None
    summary = render_summary(
        BaselineEvaluationResult(
            evaluation_run_id="test",
            timestamp=datetime(2020, 1, 1, tzinfo=UTC),
            git_commit=None,
            system="baseline",
            catalog_id="x",
            catalog_version=1,
            case_list=["001", "002"],
            configuration={},
            model_configuration={},
            per_case=[completed, failed],
            aggregate=agg,
            errors=[{"case_id": "002", "error_type": "RuntimeError", "error_message": "boom"}],
            runtime={"wall_seconds": 1.0},
        )
    )
    assert "002" in summary
    assert "headline" in summary.lower()


def test_naive_harness_uses_exact_registry_case_list(tmp_path: Path) -> None:
    json_path = tmp_path / "baseline.json"
    md_path = tmp_path / "baseline.md"
    result = run_baseline_evaluation(
        output_json=json_path,
        output_md=md_path,
        model_ids=("naive",),
        generated_at=datetime(2021, 6, 1, tzinfo=UTC),
    )
    catalog = load_catalog()
    expected = [case.case_id for case in catalog.cases]
    assert expected == list(REQUIRED_CASE_IDS)
    assert result.case_list == expected
    assert len(result.per_case) == len(expected)
    assert {row.case_id for row in result.per_case} == set(expected)
    assert json_path.is_file()
    assert md_path.is_file()
    payload = json.loads(json_path.read_text(encoding="utf-8"))
    assert payload["case_list"] == expected
    assert payload["system"] == "baseline"
    assert "wis" in payload["aggregate"]
    assert payload["aggregate"]["n_cases"] == len(expected)
    failed_ids = {row.case_id for row in result.per_case if row.status == "failed"}
    recorded_errors = {item["case_id"] for item in result.errors}
    assert failed_ids == recorded_errors
    if result.aggregate.n_cases_failed:
        assert result.aggregate.wis is None


def test_git_commit_helper() -> None:
    commit = git_commit(Path(__file__).resolve().parents[2])
    assert commit is None or (isinstance(commit, str) and len(commit) >= 7)


def test_backtest_min_train_allows_at_least_one_fold() -> None:
    assert backtest_min_train_size(16, 7, 7) == 8
    assert backtest_min_train_size(10, 14, 7) is None


def test_baseline_and_agent_use_identical_case_sets(tmp_path: Path) -> None:
    catalog = load_catalog()
    expected = [case.case_id for case in catalog.cases]
    assert expected == list(REQUIRED_CASE_IDS)
    generated_at = datetime(2021, 6, 1, tzinfo=UTC)
    baseline = run_baseline_evaluation(
        output_json=tmp_path / "baseline.json",
        output_md=tmp_path / "baseline.md",
        model_ids=("naive",),
        generated_at=generated_at,
    )
    agent = run_agent_evaluation(
        output_json=tmp_path / "agent.json",
        output_md=tmp_path / "agent.md",
        candidate_model_ids=("naive",),
        generated_at=generated_at,
    )
    assert baseline.case_list == expected
    assert agent.case_list == expected
    assert baseline.case_list == agent.case_list
    assert [row.case_id for row in baseline.per_case] == [row.case_id for row in agent.per_case]
    assert len(baseline.per_case) == len(agent.per_case) == len(expected)
    assert {row.case_id for row in baseline.per_case} == set(expected)
    assert {row.case_id for row in agent.per_case} == set(expected)
    compared = compare_evaluations(baseline, agent, generated_at=generated_at)
    assert compared.case_lists_identical is True
    assert compared.case_list == expected
    assert [row.case_id for row in compared.per_case] == expected
    failed_ids = {row.case_id for row in agent.per_case if row.status == "failed"}
    recorded = {item["case_id"] for item in agent.errors}
    assert failed_ids == recorded
    assert agent.aggregate.n_cases == len(expected)
    assert agent.aggregate.human_intervention_count == sum(
        1 for row in agent.per_case if row.review_required
    )


def test_runtime_library_pins_record_python_and_requirement_file() -> None:
    pins = runtime_library_pins()
    assert pins["python"]
    assert pins["pandas"]
    assert pins["numpy"]
    assert pins["statsmodels"]
    assert pins["pins_file"] == "backend/requirements.txt"
    assert pins["catalog_registry"] == "evaluation/cases/case_registry.yaml"
