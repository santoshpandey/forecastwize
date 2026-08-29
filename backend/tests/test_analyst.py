from __future__ import annotations

import inspect
import json
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
from app.agents.analyst import REQUIRED_SECTIONS, run_forecast_analyst
from app.agents.forecast_strategist import DatasetDiagnostics, ForecastStrategistReport
from app.agents.state import FORECAST_ANALYST_AGENT_ID, CitedClaim
from app.agents.verifier import run_verifier
from app.tools.forecasting_tools import CandidateEvalRow
from app.tools.verification_tools import ForecastSnapshot

from tests.ts_fixtures import daily_index

_TRAJECTORY_FIELDS = (
    "run_id",
    "agent_id",
    "timestamp",
    "input_state",
    "tool_requested",
    "tool_result",
    "decision",
    "evidence_ids",
    "retry_number",
    "final_status",
)


def _forecast(yhat: list[float] | None = None, *, model: str = "naive") -> ForecastSnapshot:
    values = yhat if yhat is not None else [10.0, 10.1, 10.2]
    return ForecastSnapshot(
        yhat=values,
        lower=[v - 1.5 for v in values],
        upper=[v + 1.5 for v in values],
        forecast_horizon=len(values),
        frequency="D",
        model=model,
        interval_coverage_nominal=0.95,
    )


def _section(report, section_id: str):
    return next(item for item in report.sections if item.section_id == section_id)


def _claim() -> CitedClaim:
    return CitedClaim(
        kind="observation",
        topic="backtest",
        statement="naive ranked first on official backtest WIS.",
        evidence_ids=["E-bt"],
        uncertainty="medium",
        why_uncertainty="Copied for a unit test fixture.",
    )


def _strategist() -> ForecastStrategistReport:
    return ForecastStrategistReport(
        proposed_candidate_ids=["naive", "seasonal_naive"],
        recommended_strategy_id="naive",
        selection_rule="official_backtest_wis",
        backtest_executed=True,
        comparison=[
            CandidateEvalRow(
                model_id="naive",
                official_wis=1.2,
                wis_completed_only=1.2,
                n_folds_planned=3,
                n_folds_completed=3,
                n_folds_failed=0,
                rank=1,
            ),
            CandidateEvalRow(
                model_id="seasonal_naive",
                official_wis=1.8,
                wis_completed_only=1.8,
                n_folds_planned=3,
                n_folds_completed=3,
                n_folds_failed=0,
                rank=2,
            ),
        ],
        claims=[_claim()],
        risks=[],
        investigations=[],
        evidence_ids_used=["E-bt"],
    )


def test_analyst_source_does_not_forecast_or_call_llm() -> None:
    from app.agents import analyst

    text = inspect.getsource(analyst).lower()
    assert "import fastapi" not in text
    assert "import openai" not in text
    assert "langgraph" not in text
    assert "run_baseline_forecast" not in text
    assert "yhat =" not in text


def test_missing_forecast_fails(tmp_path: Path) -> None:
    state = run_forecast_analyst(
        forecast=None,
        run_id="test-missing-fc",
        generated_at=datetime(2021, 2, 1, tzinfo=UTC),
        trajectory_path=tmp_path / "missing.jsonl",
    )
    assert state.status == "failed"
    assert state.error_type == "MissingForecast"
    assert state.report is not None
    assert [item.section_id for item in state.report.sections] == list(REQUIRED_SECTIONS)
    assert "unavailable" in state.report.markdown.lower()
    assert "holiday" not in state.report.markdown.lower()


def test_twelve_sections_cite_evidence_and_copy_yhat(tmp_path: Path) -> None:
    n = 40
    rng = np.random.default_rng(2)
    train = np.full(n, 10.0) + rng.normal(0.0, 0.8, n)
    yhat = [10.0, 10.05, 9.97, 10.02, 10.01, 9.99, 10.03]
    actuals = np.array(yhat, dtype=float) + rng.normal(0.0, 0.05, len(yhat))
    snap = _forecast(yhat)
    verified = run_verifier(
        train_values=train,
        train_timestamps=daily_index(n),
        forecast=snap,
        actuals=actuals,
        residuals=actuals - np.array(yhat),
        run_id="test-analyst-verify",
        generated_at=datetime(2021, 2, 2, tzinfo=UTC),
        persist_trajectory=False,
    )
    assert verified.report is not None
    state = run_forecast_analyst(
        forecast=snap,
        verifier_report=verified.report,
        strategist_report=_strategist(),
        diagnostics=DatasetDiagnostics(
            n_observations=n,
            frequency="D",
            trend_detected=False,
            seasonality_detected=False,
            anomalies_detected=False,
            structural_break_detected=False,
            summary="Stable-looking series in caller diagnostics.",
        ),
        run_id="test-analyst-happy",
        generated_at=datetime(2021, 2, 3, tzinfo=UTC),
        trajectory_path=tmp_path / "happy.jsonl",
    )
    assert state.status == "completed"
    report = state.report
    assert report is not None
    assert [item.section_id for item in report.sections] == list(REQUIRED_SECTIONS)
    assert report.emitted_forecast is False
    assert report.forecast_adjusted is False
    assert report.invented_business_recommendations is False
    assert report.context_available is False
    expected = _section(report, "expected_forecast")
    assert "10.05" in expected.body
    assert expected.evidence_ids
    for eid in expected.evidence_ids:
        assert eid in state.evidence
        assert eid in report.evidence_ids_used
    for section in report.sections:
        assert section.evidence_ids
        assert section.title
        for claim in section.claims:
            assert claim.evidence_ids
            for eid in claim.evidence_ids:
                assert eid in state.evidence
    interval = _section(report, "prediction_interval")
    assert "8.5" in interval.body or "8.50000" in interval.body or "8.5" in interval.body
    why = _section(report, "why_model_selected")
    assert "official backtest wis" in why.body.lower()
    assert "naive" in why.body
    context = _section(report, "context_events")
    assert "unavailable" in context.body.lower()
    assert "holiday" not in report.markdown.lower()
    assert "increase inventory" not in report.markdown.lower()
    quality = _section(report, "confidence_quality")
    assert "guarantee" in quality.body.lower() or "not" in quality.body.lower()
    lines = [
        json.loads(line)
        for line in (tmp_path / "happy.jsonl").read_text(encoding="utf-8").splitlines()
        if line
    ]
    assert lines[-1]["agent_id"] == FORECAST_ANALYST_AGENT_ID
    assert lines[-1]["final_status"] == "completed"
    for row in lines:
        for field in _TRAJECTORY_FIELDS:
            assert field in row


def test_without_verifier_quality_is_uncertain(tmp_path: Path) -> None:
    state = run_forecast_analyst(
        forecast=_forecast(),
        run_id="test-no-verifier",
        generated_at=datetime(2021, 2, 4, tzinfo=UTC),
        trajectory_path=tmp_path / "no-ver.jsonl",
    )
    report = state.report
    assert report is not None
    quality = _section(report, "confidence_quality")
    assert quality.uncertainty == "high"
    assert "not" in quality.body.lower()
    assert report.verification_overall is None
    verify = _section(report, "verification_results")
    assert "unavailable" in verify.body.lower()
    actions = _section(report, "recommended_human_actions")
    assert "verification" in actions.body.lower()
    why = _section(report, "why_model_selected")
    assert "unavailable" in why.body.lower()
    assert "superior" in why.body.lower()


def test_fail_verification_uses_cautious_language(tmp_path: Path) -> None:
    n = 20
    train = np.full(n, 10.0)
    snap = _forecast([10.0] * 6)
    verified = run_verifier(
        train_values=train,
        forecast=snap,
        actuals=np.full(6, 50.0),
        run_id="test-analyst-fail-ver",
        generated_at=datetime(2021, 2, 5, tzinfo=UTC),
        persist_trajectory=False,
    )
    assert verified.report is not None
    assert verified.report.overall_reported == "FAIL"
    state = run_forecast_analyst(
        forecast=snap,
        verifier_report=verified.report,
        run_id="test-analyst-fail",
        generated_at=datetime(2021, 2, 6, tzinfo=UTC),
        trajectory_path=tmp_path / "fail.jsonl",
    )
    report = state.report
    assert report is not None
    quality = _section(report, "confidence_quality")
    assert "not confirmed" in quality.body.lower() or "fail" in quality.body.lower()
    assert "high confidence" not in report.markdown.lower()
    assert "definitely" not in report.markdown.lower()
    actions = _section(report, "recommended_human_actions")
    assert actions.body
    assert "increase inventory" not in actions.body.lower()


def test_does_not_invent_context_or_business_actions(tmp_path: Path) -> None:
    state = run_forecast_analyst(
        forecast=_forecast(),
        run_id="test-no-context",
        generated_at=datetime(2021, 2, 7, tzinfo=UTC),
        trajectory_path=tmp_path / "nocontext.jsonl",
    )
    dump = state.report.markdown.lower() if state.report else ""
    for token in ("holiday", "promotion", "campaign", "stockout"):
        assert token not in dump
    assert "unavailable" in dump
