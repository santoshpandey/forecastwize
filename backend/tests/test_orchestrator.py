from __future__ import annotations

import inspect
import json
from datetime import UTC, datetime
from pathlib import Path

from app.agents.forecast_strategist import ForecastStrategistReport
from app.agents.orchestrator import (
    MAX_GRAPH_STEPS,
    NODE_ORDER,
    OrchestratorHooks,
    run_orchestrator,
)
from app.agents.state import (
    ORCHESTRATOR_AGENT_ID,
    ORCHESTRATOR_MAX_RETRIES,
    CitedClaim,
    EvidenceItem,
)
from app.agents.verifier import VerifierReport, VerifierState
from app.tools.data_tools import DataToolEnvelope
from app.tools.forecasting_tools import CandidateEvalRow
from app.tools.verification_tools import ForecastSnapshot, VerificationCheck

from tests.ts_fixtures import daily_index, trend_seasonal

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

_HAPPY_NODES = list(NODE_ORDER)


def _claim() -> CitedClaim:
    return CitedClaim(
        kind="observation",
        topic="verification",
        statement="Stub verification result for orchestrator tests.",
        evidence_ids=["E-v"],
        uncertainty="medium",
        why_uncertainty="Hooked verifier in a unit test.",
    )


def _verify_state(overall: str) -> VerifierState:
    check = VerificationCheck(
        check_id="V10_invalid_values",
        name="invalid values",
        result=overall,  # type: ignore[arg-type]
        severity="high" if overall == "FAIL" else "low",
        explanation=f"stub overall={overall}",
        evidence={"stub": True},
        applicable=True,
    )
    report = VerifierReport(
        overall_deterministic=overall,  # type: ignore[arg-type]
        overall_reported=overall,  # type: ignore[arg-type]
        challenged=True,
        deterministic_checks=[check],
        reported_checks=[check],
        claims=[_claim()],
        risks=[],
        investigations=[],
        evidence_ids_used=["E-v"],
    )
    return VerifierState(
        run_id="stub-verify",
        status="completed",
        overall_result=overall,  # type: ignore[arg-type]
        evidence={
            "E-v": EvidenceItem(
                evidence_id="E-v",
                tool_name="verify_forecast",
                payload={"overall_result": overall},
            )
        },
        report=report,
    )


def _sequence_verify(results: list[str]) -> OrchestratorHooks:
    queue = list(results)

    def _verify(**_kwargs: object) -> VerifierState:
        overall = queue.pop(0) if queue else results[-1]
        return _verify_state(overall)

    return OrchestratorHooks(verify=_verify)


def _forecast_hook(**kwargs: object) -> ForecastSnapshot:
    model_id = str(kwargs.get("model_id") or "naive")
    return ForecastSnapshot(
        yhat=[10.0, 10.1, 10.2],
        lower=[8.5, 8.6, 8.7],
        upper=[11.5, 11.6, 11.7],
        forecast_horizon=3,
        frequency="D",
        model=model_id,
        interval_coverage_nominal=0.95,
    )


def _backtest_hook(*, candidate_model_ids: tuple[str, ...], **_kwargs: object):
    ids = list(candidate_model_ids)
    comparison = [
        CandidateEvalRow(
            model_id=model_id,
            official_wis=1.0 + float(index),
            wis_completed_only=1.0 + float(index),
            n_folds_planned=3,
            n_folds_completed=3,
            n_folds_failed=0,
            rank=index + 1,
        )
        for index, model_id in enumerate(ids)
    ]
    return _strategist_state(comparison, recommended=ids[0])


def _backtest_hook_wis_improves_along_rank(
    *, candidate_model_ids: tuple[str, ...], **_kwargs: object
):
    """Rank 1 is selected first but has the worst WIS so a FAIL retry can improve."""
    ids = list(candidate_model_ids)
    n = len(ids)
    comparison = [
        CandidateEvalRow(
            model_id=model_id,
            official_wis=float(n - index),
            wis_completed_only=float(n - index),
            n_folds_planned=3,
            n_folds_completed=3,
            n_folds_failed=0,
            rank=index + 1,
        )
        for index, model_id in enumerate(ids)
    ]
    return _strategist_state(comparison, recommended=ids[0])


def _strategist_state(
    comparison: list[CandidateEvalRow],
    *,
    recommended: str,
):
    from app.agents.forecast_strategist import ForecastStrategistState

    ids = [row.model_id for row in comparison]
    report = ForecastStrategistReport(
        proposed_candidate_ids=ids,
        recommended_strategy_id=recommended,
        selection_rule="official_backtest_wis",
        backtest_executed=True,
        comparison=comparison,
        claims=[
            CitedClaim(
                kind="observation",
                topic="backtest",
                statement="Official backtest WIS ranking from the test hook.",
                evidence_ids=["E-bt"],
                uncertainty="medium",
                why_uncertainty="Hooked backtest in a unit test.",
            )
        ],
        risks=[],
        investigations=[],
        evidence_ids_used=["E-bt"],
    )
    return ForecastStrategistState(
        run_id="stub-backtest",
        status="completed",
        evidence={
            "E-bt": EvidenceItem(
                evidence_id="E-bt",
                tool_name="evaluate_candidates",
                payload={"recommended_strategy_id": recommended},
            )
        },
        report=report,
    )


def _run(
    tmp_path: Path,
    *,
    run_id: str,
    hooks: OrchestratorHooks,
    candidate_model_ids: tuple[str, ...] = ("naive",),
    n: int = 36,
):
    values = trend_seasonal(n)
    return run_orchestrator(
        daily_index(n),
        values,
        horizon=7,
        frequency="D",
        candidate_model_ids=candidate_model_ids,
        seed=1,
        hooks=hooks,
        run_id=run_id,
        generated_at=datetime(2021, 3, 1, tzinfo=UTC),
        trajectory_path=tmp_path / f"{run_id}.jsonl",
    )


def _assert_trajectory(path: Path) -> list[dict]:
    lines = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]
    assert lines
    assert lines[-1]["agent_id"] == ORCHESTRATOR_AGENT_ID
    for row in lines:
        for field in _TRAJECTORY_FIELDS:
            assert field in row
    return lines


def test_orchestrator_source_does_not_forecast_or_call_llm() -> None:
    from app.agents import orchestrator

    text = inspect.getsource(orchestrator).lower()
    assert "import fastapi" not in text
    assert "import openai" not in text
    assert "langgraph" not in text
    assert "yhat =" not in text
    assert ORCHESTRATOR_MAX_RETRIES == 2


def test_successful_run(tmp_path: Path) -> None:
    hooks = _sequence_verify(["PASS"])
    hooks.forecast = _forecast_hook
    hooks.backtest = _backtest_hook
    state = _run(tmp_path, run_id="orch-success", hooks=hooks)
    assert state.status == "completed"
    assert state.accepted is True
    assert state.review_required is False
    assert state.verification_ran is True
    assert state.verification_overall == "PASS"
    assert state.retry_number == 0
    assert state.nodes_visited == _HAPPY_NODES
    assert state.forecast is not None
    assert state.analyst_report is not None
    assert state.human_checkpoint is not None
    assert state.human_checkpoint.required is False
    assert state.human_checkpoint.status == "not_required"
    assert state.evidence
    assert all(eid.startswith("E") for eid in state.evidence)
    dump = json.dumps(state.model_dump(mode="json"))
    assert "trend_seasonal" not in dump
    lines = _assert_trajectory(tmp_path / "orch-success.jsonl")
    assert any(row["tool_requested"] == "verify_forecast" for row in lines)
    assert any(row["decision"] and row["decision"].get("action") == "accept" for row in lines)


def test_verification_warning(tmp_path: Path) -> None:
    hooks = _sequence_verify(["WARN"])
    hooks.forecast = _forecast_hook
    hooks.backtest = _backtest_hook
    state = _run(tmp_path, run_id="orch-warn", hooks=hooks)
    assert state.status == "waiting_for_approval"
    assert state.accepted is False
    assert state.verification_overall == "WARN"
    assert state.retry_number == 0
    assert state.human_checkpoint is not None
    assert state.human_checkpoint.required is True
    assert state.human_checkpoint.status == "waiting_for_approval"
    assert "low_forecast_confidence" in state.human_checkpoint.triggers
    assert "material_uncertainty" in state.human_checkpoint.triggers
    assert state.analyst_report is not None
    _assert_trajectory(tmp_path / "orch-warn.jsonl")


def test_human_accept_and_reject_after_warning(tmp_path: Path) -> None:
    from app.agents.checkpoint import apply_human_checkpoint
    from app.agents.state import HUMAN_AGENT_ID
    from app.evidence.logger import persist_trajectory_step

    hooks = _sequence_verify(["WARN"])
    hooks.forecast = _forecast_hook
    hooks.backtest = _backtest_hook
    path = tmp_path / "orch-human.jsonl"
    state = _run(tmp_path, run_id="orch-human", hooks=hooks)
    assert state.human_checkpoint is not None
    prior = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]
    accepted = apply_human_checkpoint(
        state.human_checkpoint,
        action="accept",
        run_id=state.run_id,
        retry_number=state.retry_number,
    )
    persist_trajectory_step(path, accepted.trajectory_step)
    assert accepted.accepted is True
    assert accepted.checkpoint.status == "approved"
    accepted_lines = [
        json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line
    ]
    assert len(accepted_lines) == len(prior) + 1
    assert accepted_lines[-1]["agent_id"] == HUMAN_AGENT_ID
    assert accepted_lines[-1]["decision"]["action"] == "accept"

    waiting_hooks = _sequence_verify(["WARN"])
    waiting_hooks.forecast = _forecast_hook
    waiting_hooks.backtest = _backtest_hook
    waiting = _run(tmp_path, run_id="orch-human-reject", hooks=waiting_hooks)
    waiting_path = tmp_path / "orch-human-reject.jsonl"
    assert waiting.human_checkpoint is not None
    rejected = apply_human_checkpoint(
        waiting.human_checkpoint,
        action="reject",
        run_id=waiting.run_id,
        retry_number=waiting.retry_number,
        note="Rejected in test.",
    )
    persist_trajectory_step(waiting_path, rejected.trajectory_step)
    assert rejected.accepted is False
    assert rejected.checkpoint.status == "rejected"
    reject_lines = [
        json.loads(line) for line in waiting_path.read_text(encoding="utf-8").splitlines() if line
    ]
    assert reject_lines[-1]["decision"]["action"] == "reject"
    assert reject_lines[-1]["decision"]["note"] == "Rejected in test."


def test_verification_fail_does_not_retry_worse_wis(tmp_path: Path) -> None:
    hooks = _sequence_verify(["FAIL"])
    hooks.forecast = _forecast_hook
    hooks.backtest = _backtest_hook
    hooks.strategy = lambda _diag: ["naive", "seasonal_naive"]
    state = _run(
        tmp_path,
        run_id="orch-no-worse-retry",
        hooks=hooks,
        candidate_model_ids=("naive", "seasonal_naive"),
    )
    assert state.nodes_visited.count("FORECAST") == 1
    assert state.nodes_visited.count("VERIFY") == 1
    assert state.retry_number == 0
    assert state.tried_strategy_ids == ["naive"]
    assert state.selected_strategy_id == "naive"
    assert not any(
        step.decision and step.decision.get("action") == "retry" for step in state.trajectory
    )
    assert state.status == "waiting_for_approval"
    assert state.review_required is True
    assert state.accepted is False
    assert state.human_checkpoint is not None
    assert state.human_checkpoint.status == "waiting_for_approval"
    assert "worse model" in state.human_checkpoint.reason
    _assert_trajectory(tmp_path / "orch-no-worse-retry.jsonl")


def test_verification_failure_retries_only_better_wis(tmp_path: Path) -> None:
    hooks = _sequence_verify(["FAIL", "PASS"])
    hooks.forecast = _forecast_hook
    hooks.backtest = _backtest_hook_wis_improves_along_rank
    hooks.strategy = lambda _diag: ["naive", "seasonal_naive"]
    state = _run(
        tmp_path,
        run_id="orch-retry-ok",
        hooks=hooks,
        candidate_model_ids=("naive", "seasonal_naive"),
    )
    assert state.status == "completed"
    assert state.accepted is True
    assert state.review_required is False
    assert state.retry_number == 1
    assert state.verification_overall == "PASS"
    assert state.selected_strategy_id == "seasonal_naive"
    assert state.tried_strategy_ids == ["naive", "seasonal_naive"]
    assert state.nodes_visited.count("FORECAST") == 2
    assert state.nodes_visited.count("RETRY_OR_ACCEPT") == 2
    assert state.analyst_report is not None
    prior_retries = [step for step in state.trajectory if step.retry_number == 0]
    later = [step for step in state.trajectory if step.retry_number == 1]
    assert prior_retries
    assert later
    _assert_trajectory(tmp_path / "orch-retry-ok.jsonl")


def test_retry_exhaustion_requires_review(tmp_path: Path) -> None:
    hooks = _sequence_verify(["FAIL", "FAIL", "FAIL"])
    hooks.forecast = _forecast_hook
    hooks.backtest = _backtest_hook_wis_improves_along_rank
    models = ("naive", "seasonal_naive", "ets")
    hooks.strategy = lambda _diag: list(models)
    state = _run(
        tmp_path,
        run_id="orch-exhaust",
        hooks=hooks,
        candidate_model_ids=models,
    )
    assert state.retry_number == ORCHESTRATOR_MAX_RETRIES
    assert state.retry_number == 2
    assert state.nodes_visited.count("FORECAST") == 3
    assert state.nodes_visited.count("VERIFY") == 3
    assert state.tried_strategy_ids == ["naive", "seasonal_naive", "ets"]
    assert state.status == "waiting_for_approval"
    assert state.review_required is True
    assert state.accepted is False
    assert state.verification_overall == "FAIL"
    assert state.human_checkpoint is not None
    assert state.human_checkpoint.required is True
    assert state.human_checkpoint.status == "waiting_for_approval"
    assert "exhausted" in state.human_checkpoint.reason.lower()
    assert "verification_failed_repeatedly" in state.human_checkpoint.triggers
    assert state.analyst_report is not None
    assert len(state.nodes_visited) < MAX_GRAPH_STEPS
    lines = _assert_trajectory(tmp_path / "orch-exhaust.jsonl")
    assert lines[-1]["final_status"] == "waiting_for_approval"
    assert any(row["decision"] and row["decision"].get("action") == "retry" for row in lines)


def test_backtest_executes_allowlist_not_strategy_shortlist(tmp_path: Path) -> None:
    from app.services.forecast_service import BASELINE_MODEL_IDS

    seen: list[tuple[str, ...]] = []

    def _spy(*, candidate_model_ids: tuple[str, ...], **kwargs: object):
        seen.append(candidate_model_ids)
        return _backtest_hook(candidate_model_ids=candidate_model_ids, **kwargs)

    hooks = _sequence_verify(["PASS"])
    hooks.forecast = _forecast_hook
    hooks.backtest = _spy
    hooks.strategy = lambda _diag: ["naive"]
    state = _run(
        tmp_path,
        run_id="orch-full-bt",
        hooks=hooks,
        candidate_model_ids=BASELINE_MODEL_IDS,
    )
    assert seen == [BASELINE_MODEL_IDS]
    assert state.proposed_candidate_ids == ["naive"]
    assert state.status == "completed"
    _assert_trajectory(tmp_path / "orch-full-bt.jsonl")


def test_tool_failure_is_preserved(tmp_path: Path) -> None:
    def _bad_profile(**_kwargs: object) -> DataToolEnvelope:
        return DataToolEnvelope(
            tool_name="inspect_series",
            ok=False,
            payload={"is_valid": False, "summary": "forced tool failure"},
            error_type="InvalidInput",
            error_message="inspect_series failed in test",
        )

    hooks = OrchestratorHooks(profile=_bad_profile)
    state = _run(tmp_path, run_id="orch-tool-fail", hooks=hooks)
    assert state.status == "failed"
    assert state.error_type == "InvalidInput"
    assert state.failures
    assert state.failures[0].node == "PROFILE"
    assert state.failures[0].error_type == "InvalidInput"
    assert state.verification_ran is False
    assert state.accepted is False
    assert "ANALYZE" not in state.nodes_visited
    assert "FORECAST" not in state.nodes_visited
    assert state.nodes_visited[-1] == "FINALIZE"
    assert len(state.nodes_visited) < MAX_GRAPH_STEPS
    lines = _assert_trajectory(tmp_path / "orch-tool-fail.jsonl")
    assert lines[-1]["final_status"] == "failed"


def test_forecast_tool_failure(tmp_path: Path) -> None:
    def _boom(**_kwargs: object) -> ForecastSnapshot:
        raise RuntimeError("forecast_fit exploded")

    hooks = _sequence_verify(["PASS"])
    hooks.forecast = _boom
    hooks.backtest = _backtest_hook
    state = _run(tmp_path, run_id="orch-fc-fail", hooks=hooks)
    assert state.status == "failed"
    assert state.error_type == "RuntimeError"
    assert any(item.node == "FORECAST" for item in state.failures)
    assert state.verification_ran is False
    _assert_trajectory(tmp_path / "orch-fc-fail.jsonl")
