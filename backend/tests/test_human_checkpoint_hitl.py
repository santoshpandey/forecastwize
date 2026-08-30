"""Human checkpoint lifecycle. Does not invent catalog decisions or change WIS."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from app.agents.checkpoint import apply_human_checkpoint
from app.agents.orchestrator import run_orchestrator
from app.evidence.logger import load_trajectory, persist_trajectory_step, redact_object
from app.evidence.trajectory_validator import validate_trajectory_file
from app.forecasting.robustness import DEFAULT_SELECTION_POLICY, EXP010_LAST_TO_EARLIER_VETO

from tests.ts_fixtures import daily_index, trend_seasonal

_CREATED = datetime(2021, 3, 1, tzinfo=UTC)


def test_checkpoint_creation_is_pending_without_human_decision(tmp_path: Path) -> None:
    path = tmp_path / "pending.jsonl"
    state = run_orchestrator(
        daily_index(36),
        trend_seasonal(36),
        horizon=7,
        frequency="D",
        seed=1,
        generated_at=_CREATED,
        run_id="hitl-pending",
        trajectory_path=path,
        persist_trajectory=True,
        case_id="demo",
    )
    assert state.status == "waiting_for_approval"
    assert state.human_checkpoint is not None
    assert state.human_checkpoint.required is True
    assert state.human_checkpoint.status == "waiting_for_approval"
    assert state.human_checkpoint.checkpoint_id == "ckpt-hitl-pending"
    records = validate_trajectory_file(
        path, expected_case_id="demo", expected_run_id="hitl-pending"
    )
    types = [row.event_type for row in records if row.event_type is not None]
    assert "HUMAN_CHECKPOINT_CREATED" in types
    assert "HUMAN_DECISION" not in types
    created = next(row for row in records if row.event_type == "HUMAN_CHECKPOINT_CREATED")
    assert created.payload is not None
    assert created.payload["checkpoint_id"] == "ckpt-hitl-pending"
    assert created.payload["checkpoint_status"] == "waiting_for_approval"
    assert DEFAULT_SELECTION_POLICY == "exp010"
    assert EXP010_LAST_TO_EARLIER_VETO == 5.0


def test_accept_persists_human_decision_then_run_completed(tmp_path: Path) -> None:
    path = tmp_path / "accept.jsonl"
    state = run_orchestrator(
        daily_index(36),
        trend_seasonal(36),
        horizon=7,
        frequency="D",
        seed=1,
        generated_at=_CREATED,
        run_id="hitl-accept",
        trajectory_path=path,
        persist_trajectory=True,
        case_id="demo",
    )
    assert state.human_checkpoint is not None
    prior = load_trajectory(path)
    decision = apply_human_checkpoint(
        state.human_checkpoint,
        action="accept",
        run_id=state.run_id,
        retry_number=state.retry_number,
        case_id="demo",
    )
    persist_trajectory_step(path, decision.trajectory_step)
    assert decision.continuation_step is not None
    persist_trajectory_step(path, decision.continuation_step)
    records = validate_trajectory_file(
        path, expected_case_id="demo", expected_run_id="hitl-accept"
    )
    assert len(records) == len(prior) + 2
    sequences = [row.sequence for row in records if row.sequence is not None]
    assert sequences == list(range(len(records)))
    event_ids = [row.event_id for row in records if row.event_id is not None]
    assert len(event_ids) == len(set(event_ids))
    human = next(row for row in records if row.event_type == "HUMAN_DECISION")
    assert human.payload is not None
    assert human.payload["decision"] == "accept"
    assert human.payload["checkpoint_id"] == state.human_checkpoint.checkpoint_id
    assert "note" not in human.payload
    assert records[-1].event_type == "RUN_COMPLETED"
    assert records[-1].payload is not None
    assert records[-1].payload["continuation_of"] == "HUMAN_DECISION"
    assert records[-1].payload["accepted"] is True
    created_idx = next(
        i for i, row in enumerate(records) if row.event_type == "HUMAN_CHECKPOINT_CREATED"
    )
    human_idx = next(i for i, row in enumerate(records) if row.event_type == "HUMAN_DECISION")
    assert created_idx < human_idx < len(records) - 1


def test_reject_and_review_paths(tmp_path: Path) -> None:
    path = tmp_path / "review.jsonl"
    state = run_orchestrator(
        daily_index(36),
        trend_seasonal(36),
        horizon=7,
        frequency="D",
        seed=1,
        generated_at=_CREATED,
        run_id="hitl-review",
        trajectory_path=path,
        persist_trajectory=True,
    )
    assert state.human_checkpoint is not None
    reviewed = apply_human_checkpoint(
        state.human_checkpoint,
        action="review",
        run_id=state.run_id,
        retry_number=state.retry_number,
        note="Need another look.",
    )
    persist_trajectory_step(path, reviewed.trajectory_step)
    assert reviewed.continuation_step is None
    assert reviewed.run_status == "waiting_for_approval"
    after_review = load_trajectory(path)
    assert after_review[-1].event_type == "HUMAN_DECISION"
    assert after_review[-1].payload is not None
    assert after_review[-1].payload["decision"] == "review"

    rejected = apply_human_checkpoint(
        reviewed.checkpoint,
        action="reject",
        run_id=state.run_id,
        retry_number=state.retry_number,
        note="Do not adopt this forecast.",
    )
    persist_trajectory_step(path, rejected.trajectory_step)
    assert rejected.continuation_step is not None
    persist_trajectory_step(path, rejected.continuation_step)
    records = load_trajectory(path)
    decisions = [
        row.payload.get("decision")
        for row in records
        if row.event_type == "HUMAN_DECISION" and row.payload
    ]
    assert decisions == ["review", "reject"]
    assert records[-1].event_type == "RUN_COMPLETED"
    assert records[-1].payload is not None
    assert records[-1].payload["accepted"] is False


def test_human_decision_note_is_redacted(tmp_path: Path) -> None:
    path = tmp_path / "redact.jsonl"
    state = run_orchestrator(
        daily_index(36),
        trend_seasonal(36),
        horizon=7,
        frequency="D",
        seed=1,
        generated_at=_CREATED,
        run_id="hitl-redact",
        trajectory_path=path,
        persist_trajectory=True,
    )
    assert state.human_checkpoint is not None
    decision = apply_human_checkpoint(
        state.human_checkpoint,
        action="accept",
        run_id=state.run_id,
        retry_number=state.retry_number,
        note="api_key=sk-secretvalue123456",
    )
    persist_trajectory_step(path, decision.trajectory_step)
    text = path.read_text(encoding="utf-8")
    assert "sk-secretvalue123456" not in text
    cleaned = redact_object(decision.trajectory_step.payload)
    assert isinstance(cleaned, dict)
    assert "sk-secretvalue123456" not in str(cleaned)


def test_official_catalog_still_has_no_fabricated_human_decisions() -> None:
    official = (
        Path(__file__).resolve().parents[2]
        / "evaluation"
        / "results"
        / "trajectories"
        / "agent-20260830T030413Z"
    )
    if not official.is_dir():
        return
    files = sorted(official.glob("case_*.jsonl"))
    assert len(files) == 12
    for path in files:
        types = {row.event_type for row in load_trajectory(path)}
        assert "HUMAN_DECISION" not in types
        assert "HUMAN_CHECKPOINT_CREATED" in types
