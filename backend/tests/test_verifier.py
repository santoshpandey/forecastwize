from __future__ import annotations

import inspect
import json
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pytest
from app.agents.state import VERIFIER_AGENT_ID, CitedClaim
from app.agents.verifier import CheckOverride, VerifierReport, run_verifier
from app.forecasting.base import ForecastInterfaceError
from app.tools.verification_tools import (
    CHECK_EXTREME_GROWTH,
    CHECK_FORECAST_BOUNDS,
    CHECK_HISTORICAL_RANGE,
    CHECK_INTERVAL_COVERAGE,
    CHECK_INTERVAL_WIDTH,
    CHECK_INVALID_VALUES,
    CHECK_REGIME_CHANGE,
    CHECK_RESIDUAL_DIAGNOSTICS,
    CHECK_SEASONALITY_CONSISTENCY,
    CHECK_TREND_CONSISTENCY,
    ForecastSnapshot,
    VerificationCheck,
    VerifyForecastSpec,
    reject_unknown_verification_tool,
    run_verify_forecast_tool,
)
from pydantic import ValidationError

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


def _snap(
    yhat: list[float],
    *,
    width: float = 1.0,
    horizon: int | None = None,
    lower: list[float] | None = None,
    upper: list[float] | None = None,
) -> ForecastSnapshot:
    h = horizon if horizon is not None else len(yhat)
    lo = lower if lower is not None else [v - width for v in yhat]
    hi = upper if upper is not None else [v + width for v in yhat]
    return ForecastSnapshot(
        yhat=yhat,
        lower=lo,
        upper=hi,
        forecast_horizon=h,
        frequency="D",
        model="adversarial",
        interval_coverage_nominal=0.95,
    )


def _result_of(checks: list[VerificationCheck], check_id: str) -> str:
    return next(item.result for item in checks if item.check_id == check_id)


def _claim() -> CitedClaim:
    return CitedClaim(
        kind="observation",
        topic="verification",
        statement="placeholder",
        evidence_ids=["E1"],
        uncertainty="low",
        why_uncertainty="test",
    )


def test_verification_source_has_no_fastapi_or_llm() -> None:
    from app.agents import verifier
    from app.tools import verification_tools

    for module in (verifier, verification_tools):
        text = inspect.getsource(module).lower()
        assert "import fastapi" not in text
        assert "import openai" not in text
        assert "langgraph" not in text
        assert "run_baseline_forecast" not in text


def test_unknown_verification_tool_rejected() -> None:
    with pytest.raises(ForecastInterfaceError, match="Unknown tool"):
        reject_unknown_verification_tool("llm_override")


def test_missing_forecast_fails(tmp_path: Path) -> None:
    state = run_verifier(
        train_values=np.ones(20),
        forecast=None,
        run_id="test-missing-fc",
        generated_at=datetime(2021, 1, 1, tzinfo=UTC),
        trajectory_path=tmp_path / "missing.jsonl",
    )
    assert state.status == "failed"
    assert state.error_type == "MissingForecast"
    assert state.report is not None
    assert state.report.overall_reported == "FAIL"


def test_does_not_mutate_inputs() -> None:
    train = np.array([1.0, 2.0, 3.0, 4.0], dtype=float)
    original = train.copy()
    snap = _snap([4.0, 4.0])
    yhat_original = list(snap.yhat)
    env = run_verify_forecast_tool(train_values=train, forecast=snap)
    assert env.ok is True
    np.testing.assert_array_equal(train, original)
    assert snap.yhat == yhat_original


def test_happy_path_does_not_falsify_stable_forecast(tmp_path: Path) -> None:
    n = 40
    horizon = 7
    rng = np.random.default_rng(1)
    train = np.full(n, 10.0) + rng.normal(0.0, 0.8, n)
    yhat = [10.0] * horizon
    actuals = np.array([10.02, 9.97, 10.01, 10.0, 9.99, 10.03, 10.0])
    residuals = actuals - np.array(yhat)
    state = run_verifier(
        train_values=train,
        train_timestamps=daily_index(n),
        forecast=_snap(yhat, width=1.5),
        actuals=actuals,
        residuals=residuals,
        run_id="test-happy",
        generated_at=datetime(2021, 1, 2, tzinfo=UTC),
        trajectory_path=tmp_path / "happy.jsonl",
    )
    assert state.status == "completed"
    report = state.report
    assert report is not None
    assert report.emitted_forecast is False
    assert report.forecast_adjusted is False
    assert report.overrides == []
    assert report.overall_deterministic == report.overall_reported
    assert report.overall_reported != "FAIL"
    by_id = {item.check_id: item.result for item in report.deterministic_checks}
    assert by_id[CHECK_INVALID_VALUES] == "PASS"
    assert by_id[CHECK_FORECAST_BOUNDS] == "PASS"
    assert by_id[CHECK_EXTREME_GROWTH] == "PASS"
    lines = [
        json.loads(line)
        for line in (tmp_path / "happy.jsonl").read_text(encoding="utf-8").splitlines()
        if line
    ]
    assert lines[-1]["agent_id"] == VERIFIER_AGENT_ID
    assert any(row["tool_requested"] == "verify_forecast" for row in lines)
    for row in lines:
        for field in _TRAJECTORY_FIELDS:
            assert field in row


def test_adversarial_invalid_values() -> None:
    env = run_verify_forecast_tool(
        train_values=np.ones(12),
        forecast=_snap([1.0, float("nan"), 1.0]),
    )
    assert env.ok is True
    assert env.payload["overall_result"] == "FAIL"
    checks = [VerificationCheck.model_validate(item) for item in env.payload["checks"]]
    assert _result_of(checks, CHECK_INVALID_VALUES) == "FAIL"


def test_adversarial_bounds_violation() -> None:
    env = run_verify_forecast_tool(
        train_values=np.ones(12) * 5.0,
        forecast=_snap([10.0, 10.0], lower=[0.0, 0.0], upper=[1.0, 1.0]),
    )
    checks = [VerificationCheck.model_validate(item) for item in env.payload["checks"]]
    assert _result_of(checks, CHECK_FORECAST_BOUNDS) == "FAIL"
    assert env.payload["overall_result"] == "FAIL"


def test_adversarial_historical_range_and_growth() -> None:
    train = np.linspace(8.0, 12.0, 30)
    env = run_verify_forecast_tool(
        train_values=train,
        forecast=_snap([800.0, 900.0, 1000.0], width=10.0),
    )
    checks = [VerificationCheck.model_validate(item) for item in env.payload["checks"]]
    assert _result_of(checks, CHECK_HISTORICAL_RANGE) == "FAIL"
    assert _result_of(checks, CHECK_EXTREME_GROWTH) == "FAIL"


def test_adversarial_trend_reversal() -> None:
    train = np.linspace(0.0, 50.0, 40)
    yhat = [48.0, 40.0, 30.0, 20.0, 10.0, 0.0, -10.0]
    env = run_verify_forecast_tool(
        train_values=train,
        train_timestamps=daily_index(40),
        forecast=_snap(yhat, width=2.0),
    )
    checks = [VerificationCheck.model_validate(item) for item in env.payload["checks"]]
    assert _result_of(checks, CHECK_TREND_CONSISTENCY) == "FAIL"


def test_adversarial_inverted_seasonality() -> None:
    n = 56
    t = np.arange(n, dtype=float)
    train = 10.0 + 5.0 * np.sin(2.0 * np.pi * t / 7.0)
    last = train[-7:]
    yhat = list(20.0 - last)
    env = run_verify_forecast_tool(
        train_values=train,
        train_timestamps=daily_index(n),
        forecast=_snap(yhat, width=1.0),
        spec=VerifyForecastSpec(seasonal_period=7),
    )
    checks = [VerificationCheck.model_validate(item) for item in env.payload["checks"]]
    assert _result_of(checks, CHECK_SEASONALITY_CONSISTENCY) == "FAIL"


def test_adversarial_residual_bias() -> None:
    train = np.full(20, 10.0)
    yhat = [10.0] * 8
    actuals = np.full(8, 20.0)
    env = run_verify_forecast_tool(
        train_values=train,
        forecast=_snap(yhat, width=12.0),
        actuals=actuals,
    )
    checks = [VerificationCheck.model_validate(item) for item in env.payload["checks"]]
    assert _result_of(checks, CHECK_RESIDUAL_DIAGNOSTICS) == "FAIL"


def test_adversarial_interval_coverage() -> None:
    train = np.full(20, 10.0)
    yhat = [10.0] * 8
    actuals = np.full(8, 50.0)
    env = run_verify_forecast_tool(
        train_values=train,
        forecast=_snap(yhat, width=1.0),
        actuals=actuals,
    )
    checks = [VerificationCheck.model_validate(item) for item in env.payload["checks"]]
    assert _result_of(checks, CHECK_INTERVAL_COVERAGE) == "FAIL"


def test_adversarial_zero_width_intervals() -> None:
    rng = np.random.default_rng(0)
    train = rng.normal(10.0, 2.0, 30)
    yhat = [10.0] * 6
    env = run_verify_forecast_tool(
        train_values=train,
        forecast=_snap(yhat, lower=yhat, upper=yhat),
    )
    checks = [VerificationCheck.model_validate(item) for item in env.payload["checks"]]
    assert _result_of(checks, CHECK_INTERVAL_WIDTH) == "FAIL"


def test_adversarial_regime_change_old_mean() -> None:
    train = np.concatenate([np.full(24, 0.0), np.full(24, 20.0)])
    yhat = [0.0, 0.0, 0.0, 0.0]
    env = run_verify_forecast_tool(
        train_values=train,
        train_timestamps=daily_index(48),
        forecast=_snap(yhat, width=1.0),
    )
    checks = [VerificationCheck.model_validate(item) for item in env.payload["checks"]]
    result = _result_of(checks, CHECK_REGIME_CHANGE)
    assert result in {"FAIL", "WARN"}
    assert result != "PASS"


def test_coverage_without_actuals_is_warn_not_pass() -> None:
    env = run_verify_forecast_tool(
        train_values=np.full(20, 10.0),
        forecast=_snap([10.0, 10.0], width=1.0),
    )
    checks = [VerificationCheck.model_validate(item) for item in env.payload["checks"]]
    coverage = next(item for item in checks if item.check_id == CHECK_INTERVAL_COVERAGE)
    assert coverage.result == "WARN"
    assert coverage.applicable is False


def test_silent_override_is_rejected() -> None:
    fail = VerificationCheck(
        check_id=CHECK_INVALID_VALUES,
        name="missing/invalid forecast values",
        result="FAIL",
        severity="high",
        explanation="nan",
        evidence={},
    )
    pretend_pass = fail.model_copy(update={"result": "PASS"})
    with pytest.raises(ValidationError, match="without a recorded override"):
        VerifierReport(
            overall_deterministic="FAIL",
            overall_reported="PASS",
            challenged=False,
            deterministic_checks=[fail],
            reported_checks=[pretend_pass],
            overrides=[],
            claims=[_claim()],
            risks=[],
            investigations=[],
            evidence_ids_used=["E1"],
        )


def test_override_requires_reason_and_is_recorded(tmp_path: Path) -> None:
    with pytest.raises(ValidationError):
        CheckOverride(
            check_id=CHECK_INVALID_VALUES,
            deterministic_result="FAIL",
            interpreted_result="PASS",
            reason="   ",
        )
    train = np.ones(12)
    snap = _snap([1.0, float("nan")])
    override = CheckOverride(
        check_id=CHECK_INVALID_VALUES,
        deterministic_result="FAIL",
        interpreted_result="WARN",
        reason="Holdout pipeline injects a sentinel NaN that is not a model output.",
    )
    state = run_verifier(
        train_values=train,
        forecast=snap,
        overrides=[override],
        run_id="test-override",
        generated_at=datetime(2021, 1, 3, tzinfo=UTC),
        trajectory_path=tmp_path / "override.jsonl",
    )
    report = state.report
    assert report is not None
    det = _result_of(report.deterministic_checks, CHECK_INVALID_VALUES)
    reported = _result_of(report.reported_checks, CHECK_INVALID_VALUES)
    assert det == "FAIL"
    assert reported == "WARN"
    assert report.overrides[0].reason.startswith("Holdout pipeline")
    assert report.overall_deterministic == "FAIL"
