"""Observational trajectory persistence. Does not change forecast math."""

from __future__ import annotations

import inspect
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from app.agents.checkpoint import HumanCheckpoint, apply_human_checkpoint
from app.agents.orchestrator import run_orchestrator
from app.evidence.logger import load_trajectory
from app.evidence.trajectory import TRAJECTORY_SCHEMA_VERSION
from app.evidence.trajectory_validator import (
    TrajectoryValidationError,
    validate_evidence_references,
    validate_trajectory_file,
)
from app.forecasting.robustness import DEFAULT_SELECTION_POLICY, EXP010_LAST_TO_EARLIER_VETO
from evaluation.cases.generators import REQUIRED_CASE_IDS, load_catalog
from app.forecasting.missing_policy import apply_linear_interpolate_train
from evaluation.cases.generators.catalog import DATA_DIR
from evaluation.run_agent import run_agent_evaluation
from evaluation.run_baseline import seasonal_period_for, split_train_holdout

from tests.ts_fixtures import daily_index, trend_seasonal

_CREATED = datetime(2021, 6, 1, tzinfo=UTC)


def _event_types(path: Path) -> list[str]:
    return [row.event_type for row in load_trajectory(path) if row.event_type is not None]


def test_trajectory_modules_do_not_forecast() -> None:
    from app.evidence import logger, trajectory, trajectory_validator

    for module in (logger, trajectory, trajectory_validator):
        text = inspect.getsource(module).lower()
        assert "import fastapi" not in text
        assert "import openai" not in text
        assert "yhat =" not in text


def test_official_eval_persist_default_is_on() -> None:
    assert inspect.signature(run_agent_evaluation).parameters["persist_trajectory"].default is True


def test_one_trajectory_per_case_from_actual_eval(tmp_path: Path) -> None:
    result = run_agent_evaluation(
        output_json=tmp_path / "agent.json",
        output_md=tmp_path / "agent.md",
        candidate_model_ids=("naive",),
        generated_at=_CREATED,
        persist_trajectory=True,
    )
    traj_dir = tmp_path / "trajectories" / result.evaluation_run_id
    assert (traj_dir / "manifest.json").is_file()
    manifest = json.loads((traj_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["trajectory_schema_version"] == TRAJECTORY_SCHEMA_VERSION
    assert manifest["selection_policy"] == DEFAULT_SELECTION_POLICY
    assert manifest["case_list"] == list(REQUIRED_CASE_IDS)
    files = sorted(traj_dir.glob("case_*.jsonl"))
    assert [path.name for path in files] == [f"case_{cid}.jsonl" for cid in REQUIRED_CASE_IDS]
    for case_id in REQUIRED_CASE_IDS:
        records = validate_trajectory_file(
            traj_dir / f"case_{case_id}.jsonl",
            expected_case_id=case_id,
            expected_run_id=f"{result.evaluation_run_id}-{case_id}",
        )
        validate_evidence_references(records)
        types = {row.event_type for row in records}
        assert "RUN_STARTED" in types
        assert types & {"RUN_COMPLETED", "RUN_FAILED"}
        assert "HUMAN_DECISION" not in types
        assert "RETRY_REQUESTED" not in types
        assert "RETRY_STARTED" not in types


def test_agent_tool_backtest_verify_and_checkpoint_events(tmp_path: Path) -> None:
    path = tmp_path / "case_live.jsonl"
    state = run_orchestrator(
        daily_index(36),
        trend_seasonal(36),
        horizon=7,
        frequency="D",
        seed=1,
        run_id="traj-live-001",
        generated_at=_CREATED,
        trajectory_path=path,
        persist_trajectory=True,
        case_id="001",
        evaluation_metadata={"git_commit": "test", "selection_policy": "exp010"},
    )
    assert state.forecast is not None
    records = validate_trajectory_file(path, expected_case_id="001", expected_run_id="traj-live-001")
    types = _event_types(path)
    assert "RUN_STARTED" in types
    assert "AGENT_STARTED" in types
    assert "TOOL_COMPLETED" in types
    assert "BACKTEST_COMPLETED" in types
    assert "ROBUSTNESS_ANALYZED" in types
    assert "MODEL_SELECTED" in types
    assert "FORECAST_STARTED" in types
    assert "FORECAST_COMPLETED" in types
    assert "VERIFICATION_STARTED" in types
    assert "VERIFICATION_COMPLETED" in types
    assert "RUN_COMPLETED" in types
    assert types.count("RETRY_REQUESTED") == 0
    assert "HUMAN_DECISION" not in types
    if state.human_checkpoint is not None and state.human_checkpoint.required:
        assert "HUMAN_CHECKPOINT_CREATED" in types
        pending = [
            row
            for row in records
            if row.event_type == "HUMAN_CHECKPOINT_CREATED"
        ]
        assert pending
        assert pending[0].payload is not None
        assert pending[0].payload.get("checkpoint_status") == "waiting_for_approval"
    assert any(row.tool_requested == "evaluate_candidates" for row in records)
    assert any(row.tool_requested == "analyze_backtest_robustness" for row in records)
    assert any(row.agent_id == "forecast_strategist" for row in records)
    assert any(row.agent_id == "verifier" for row in records)
    assert all(row.case_id == "001" for row in records)
    assert all(row.run_id == "traj-live-001" for row in records)


def test_case_012_records_actual_robustness_veto(tmp_path: Path) -> None:
    catalog = load_catalog()
    case = next(item for item in catalog.cases if item.case_id == "012")
    from app.data.schemas import TIMESTAMP_COL, VALUE_COL
    from app.data.validator import inspect_csv

    frame = inspect_csv(DATA_DIR / case.csv_filename).derived
    train_ts, train_y, _, _ = split_train_holdout(
        frame[TIMESTAMP_COL],
        frame[VALUE_COL].to_numpy(dtype=float),
        history_length=case.history_length,
        forecast_horizon=case.forecast_horizon,
    )
    train_y, _ = apply_linear_interpolate_train(train_ts, train_y)
    path = tmp_path / "case_012.jsonl"
    state = run_orchestrator(
        train_ts,
        train_y,
        horizon=case.forecast_horizon,
        frequency=case.frequency,
        seasonal_period=seasonal_period_for(case),
        seed=case.random_seed,
        run_id="traj-012",
        generated_at=_CREATED,
        trajectory_path=path,
        persist_trajectory=True,
        case_id="012",
    )
    records = validate_trajectory_file(path, expected_case_id="012", expected_run_id="traj-012")
    types = _event_types(path)
    assert "ROBUSTNESS_ANALYZED" in types
    assert "MODEL_VETOED" in types
    assert "MODEL_SELECTED" in types
    vetoed = [
        row.payload.get("model")
        for row in records
        if row.event_type == "MODEL_VETOED" and row.payload
    ]
    assert "ets" in vetoed
    selected = next(row for row in records if row.event_type == "MODEL_SELECTED")
    assert selected.payload is not None
    assert selected.payload.get("model") == state.selected_strategy_id
    assert state.retry_number == 0
    assert "RETRY_REQUESTED" not in types
    assert "HUMAN_DECISION" not in types


def test_no_fake_human_decision_until_apply_checkpoint() -> None:
    waiting = HumanCheckpoint(
        required=True,
        status="waiting_for_approval",
        reason="Verification WARN.",
        evidence_ids=["E1"],
        triggers=["low_forecast_confidence"],
    )
    decision = apply_human_checkpoint(
        waiting,
        action="accept",
        run_id="human-demo",
        retry_number=0,
        case_id="001",
    )
    assert decision.trajectory_step.event_type == "HUMAN_DECISION"
    assert decision.trajectory_step.payload is not None
    assert decision.trajectory_step.payload["decision"] == "accept"
    assert decision.trajectory_step.payload["checkpoint_id"] == "ckpt-human-demo"
    assert "note" not in decision.trajectory_step.payload
    assert decision.continuation_step is not None
    assert decision.continuation_step.event_type == "RUN_COMPLETED"


def test_validator_rejects_bad_sequence(tmp_path: Path) -> None:
    path = tmp_path / "bad.jsonl"
    path.write_text("{not json}\n", encoding="utf-8")
    with pytest.raises(TrajectoryValidationError, match="invalid JSONL"):
        validate_trajectory_file(path)


def test_interactive_demo_trajectory_validates_without_catalog_case_id() -> None:
    demo = (
        Path(__file__).resolve().parents[2]
        / "evaluation"
        / "artifacts"
        / "human-demo"
        / "run_f4c8529410f148e8a6f4973abf3440ee"
        / "trajectory.jsonl"
    )
    if not demo.is_file():
        pytest.skip("interactive demo artifact is not present")
    records = validate_trajectory_file(
        demo,
        expected_run_id="run_f4c8529410f148e8a6f4973abf3440ee",
        require_case_id=False,
    )
    types = [row.event_type for row in records]
    assert "HUMAN_CHECKPOINT_CREATED" in types
    assert "HUMAN_DECISION" in types
    human = next(row for row in records if row.event_type == "HUMAN_DECISION")
    assert human.payload is not None
    assert human.payload["decision"] == "accept"
    assert human.payload["checkpoint_id"] == "ckpt-run_f4c8529410f148e8a6f4973abf3440ee"
    assert "note" not in human.payload
    assert records[-1].event_type == "RUN_COMPLETED"
    assert records[-1].payload is not None
    assert records[-1].payload["continuation_of"] == "HUMAN_DECISION"


def test_persist_does_not_change_forecast_numbers(tmp_path: Path) -> None:
    kwargs = {
        "horizon": 7,
        "frequency": "D",
        "seed": 1,
        "generated_at": _CREATED,
        "case_id": "001",
    }
    values = trend_seasonal(36)
    index = daily_index(36)
    off = run_orchestrator(
        index,
        values,
        run_id="num-off",
        persist_trajectory=False,
        **kwargs,
    )
    on = run_orchestrator(
        index,
        values,
        run_id="num-on",
        persist_trajectory=True,
        trajectory_path=tmp_path / "on.jsonl",
        **kwargs,
    )
    assert off.selected_strategy_id == on.selected_strategy_id
    assert off.verification_overall == on.verification_overall
    assert off.retry_number == on.retry_number
    assert off.forecast is not None and on.forecast is not None
    assert list(off.forecast.yhat) == list(on.forecast.yhat)
    assert list(off.forecast.lower) == list(on.forecast.lower)
    assert list(off.forecast.upper) == list(on.forecast.upper)
    assert EXP010_LAST_TO_EARLIER_VETO == 5.0
    assert DEFAULT_SELECTION_POLICY == "exp010"


def test_secrets_are_redacted_in_persisted_events(tmp_path: Path) -> None:
    from app.agents.state import TrajectoryStep
    from app.evidence.logger import persist_trajectory_step

    path = tmp_path / "secret.jsonl"
    persist_trajectory_step(
        path,
        TrajectoryStep(
            run_id="secret-run",
            agent_id="orchestrator",
            timestamp=_CREATED,
            input_state={"api_key": "sk-secretvalue123456", "node": "START"},
            tool_requested=None,
            tool_result=None,
            decision={"note": "password=hunter2"},
            evidence_ids=["E1"],
            retry_number=0,
            final_status="running",
            case_id="001",
            event_type="RUN_STARTED",
            actor="orchestrator",
        ),
    )
    text = path.read_text(encoding="utf-8")
    assert "sk-secretvalue123456" not in text
    assert "hunter2" not in text
    record = load_trajectory(path)[0]
    assert record.event_id == "secret-run:0"
    assert record.sequence == 0
