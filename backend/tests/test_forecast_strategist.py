from __future__ import annotations

import inspect
import json
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
from app.agents.forecast_strategist import (
    BusinessContext,
    DatasetDiagnostics,
    propose_candidate_ids,
    run_forecast_strategist,
)
from app.agents.state import FORECAST_STRATEGIST_AGENT_ID
from app.forecasting.base import ForecastInterfaceError
from app.tools.forecasting_tools import reject_unknown_forecast_tool

from tests.ts_fixtures import daily_index, trend_seasonal


def _seasonal_diagnostics(n: int) -> DatasetDiagnostics:
    return DatasetDiagnostics(
        n_observations=n,
        frequency="D",
        seasonal_period=7,
        trend_detected=False,
        seasonality_detected=True,
        anomalies_detected=False,
        structural_break_detected=False,
        n_missing_values=0,
        forecastability="adequate",
        detective_evidence_ids=["E-diag"],
        summary="Caller-supplied seasonal diagnostics.",
    )


def test_strategist_source_does_not_forecast_or_call_llm() -> None:
    from app.agents import forecast_strategist

    text = inspect.getsource(forecast_strategist).lower()
    assert "import fastapi" not in text
    assert "import openai" not in text
    assert "langgraph" not in text
    assert "run_baseline_forecast" not in text
    assert "yhat =" not in text


def test_unknown_tool_rejected() -> None:
    try:
        reject_unknown_forecast_tool("auto_arima")
        raise AssertionError("expected reject")
    except ForecastInterfaceError as exc:
        assert "Unknown tool" in str(exc)


def test_propose_candidates_is_not_a_winner() -> None:
    seasonal = propose_candidate_ids(
        DatasetDiagnostics(n_observations=40, seasonality_detected=True)
    )
    assert seasonal[0] == "naive"
    assert "seasonal_naive" in seasonal
    trend = propose_candidate_ids(DatasetDiagnostics(n_observations=40, trend_detected=True))
    assert "arima" in trend
    assert "naive" in trend


def test_missing_diagnostics(tmp_path: Path) -> None:
    n = 30
    state = run_forecast_strategist(
        daily_index(n),
        np.arange(n, dtype=float),
        horizon=7,
        frequency="D",
        diagnostics=None,
        run_id="test-missing-diag",
        generated_at=datetime(2021, 1, 1, tzinfo=UTC),
        trajectory_path=tmp_path / "missing.jsonl",
    )
    assert state.status == "failed"
    assert state.error_type == "MissingDiagnostics"
    assert state.report is not None
    assert state.report.recommended_strategy_id is None
    assert state.report.backtest_executed is False
    assert state.report.emitted_forecast is False
    empty = DatasetDiagnostics()
    state2 = run_forecast_strategist(
        daily_index(n),
        np.arange(n, dtype=float),
        horizon=7,
        frequency="D",
        diagnostics=empty,
        run_id="test-empty-diag",
        generated_at=datetime(2021, 1, 1, tzinfo=UTC),
        trajectory_path=tmp_path / "empty.jsonl",
    )
    assert state2.error_type == "MissingDiagnostics"


def test_unsupported_model(tmp_path: Path) -> None:
    n = 30
    state = run_forecast_strategist(
        daily_index(n),
        np.arange(n, dtype=float),
        horizon=7,
        frequency="D",
        diagnostics=_seasonal_diagnostics(n),
        candidate_model_ids=("prophet",),
        run_id="test-unsupported",
        generated_at=datetime(2021, 1, 1, tzinfo=UTC),
        trajectory_path=tmp_path / "unsupported.jsonl",
    )
    assert state.status == "failed"
    assert state.error_type == "UnsupportedModel"
    assert state.report is not None
    assert state.report.recommended_strategy_id is None
    assert state.report.backtest_executed is False


def test_insufficient_data(tmp_path: Path) -> None:
    n = 6
    state = run_forecast_strategist(
        daily_index(n),
        np.arange(n, dtype=float),
        horizon=7,
        frequency="D",
        diagnostics=_seasonal_diagnostics(n),
        candidate_model_ids=("naive",),
        run_id="test-short",
        generated_at=datetime(2021, 1, 1, tzinfo=UTC),
        trajectory_path=tmp_path / "short.jsonl",
    )
    assert state.status == "failed"
    assert state.error_type == "InsufficientData"
    assert state.report is not None
    assert state.report.recommended_strategy_id is None
    assert state.report.backtest_executed is False


def test_failed_model_execution_does_not_claim_superior(tmp_path: Path) -> None:
    n = 24
    values = np.arange(n, dtype=float)
    original = values.copy()
    state = run_forecast_strategist(
        daily_index(n),
        values,
        horizon=2,
        frequency="D",
        diagnostics=_seasonal_diagnostics(n),
        candidate_model_ids=("seasonal_naive",),
        seasonal_period=40,
        run_id="test-failed-model",
        generated_at=datetime(2021, 1, 1, tzinfo=UTC),
        trajectory_path=tmp_path / "failed.jsonl",
    )
    np.testing.assert_array_equal(values, original)
    assert state.report is not None
    assert state.report.recommended_strategy_id is None
    assert state.report.selection_rule == "none"
    dump = json.dumps(state.report.model_dump(mode="json"))
    assert "yhat" not in dump
    if state.status == "completed":
        assert state.report.backtest_executed is True
        assert any(row.n_folds_failed for row in state.report.comparison)
    else:
        assert state.error_type in {"FailedModelExecution", "InsufficientData"}


def test_recommendation_requires_backtest_evidence(tmp_path: Path) -> None:
    n = 42
    t = np.arange(n, dtype=float)
    values = 10.0 + 3.0 * np.sin(2.0 * np.pi * t / 7.0)
    original = values.copy()
    traj = tmp_path / "ok.jsonl"
    state = run_forecast_strategist(
        daily_index(n),
        values,
        horizon=7,
        frequency="D",
        diagnostics=_seasonal_diagnostics(n),
        context=BusinessContext(has_event_column=False, notes=None),
        candidate_model_ids=("naive", "seasonal_naive"),
        seasonal_period=7,
        seed=3,
        run_id="test-ok",
        generated_at=datetime(2021, 2, 1, tzinfo=UTC),
        trajectory_path=traj,
    )
    np.testing.assert_array_equal(values, original)
    assert state.status == "completed"
    assert state.report is not None
    report = state.report
    assert report.emitted_forecast is False
    assert report.modified_dataset is False
    assert report.backtest_executed is True
    assert report.selection_rule == "official_backtest_wis"
    assert report.recommended_strategy_id in {"naive", "seasonal_naive"}
    assert "yhat" not in report.model_dump()
    hyps = [c for c in report.claims if c.kind == "hypothesis" and c.topic == "candidates"]
    assert hyps
    assert "not a claim" in hyps[0].statement.lower() or "not a claim" in hyps[0].statement
    winner_claims = [c for c in report.claims if c.kind == "observation" and c.topic == "strategy"]
    assert winner_claims
    eval_eids = [
        eid for eid, item in state.evidence.items() if item.tool_name == "evaluate_candidates"
    ]
    assert eval_eids
    assert eval_eids[0] in winner_claims[0].evidence_ids
    win = next(row for row in report.comparison if row.model_id == report.recommended_strategy_id)
    assert win.rank == 1
    assert win.official_wis is not None
    assert "promo" not in json.dumps(report.model_dump(mode="json")).lower()
    lines = [json.loads(line) for line in traj.read_text(encoding="utf-8").splitlines() if line]
    assert lines[-1]["final_status"] == "completed"
    assert lines[-1]["agent_id"] == FORECAST_STRATEGIST_AGENT_ID
    assert any(row["tool_requested"] == "evaluate_candidates" for row in lines)


def test_context_does_not_invent_events(tmp_path: Path) -> None:
    n = 36
    state = run_forecast_strategist(
        daily_index(n),
        trend_seasonal(n),
        horizon=7,
        frequency="D",
        diagnostics=_seasonal_diagnostics(n),
        context=BusinessContext(has_event_column=True, n_event_non_null=4, notes="provided"),
        candidate_model_ids=("naive",),
        seed=1,
        run_id="test-context",
        generated_at=datetime(2021, 3, 1, tzinfo=UTC),
        trajectory_path=tmp_path / "ctx.jsonl",
    )
    assert state.status == "completed"
    assert state.report is not None
    ctx = [c for c in state.report.claims if c.topic == "context"]
    assert ctx
    assert "invent" in ctx[0].statement.lower() or "provided" in ctx[0].statement.lower()
    assert "holiday" not in ctx[0].statement.lower()
