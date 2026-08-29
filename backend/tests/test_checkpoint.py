from __future__ import annotations

import pytest
from app.agents.checkpoint import (
    CheckpointDecisionError,
    HumanCheckpoint,
    ProposedTransform,
    apply_human_checkpoint,
    collect_checkpoint_triggers,
)
from app.agents.state import HUMAN_AGENT_ID


def _waiting(**kwargs: object) -> HumanCheckpoint:
    payload = {
        "required": True,
        "status": "waiting_for_approval",
        "reason": "Verification failed repeatedly (retries exhausted).",
        "evidence_ids": ["E1"],
        "triggers": ["verification_failed_repeatedly"],
        "source_data_unmodified": True,
    }
    payload.update(kwargs)
    return HumanCheckpoint.model_validate(payload)


def test_triggers_for_each_required_gate() -> None:
    data = collect_checkpoint_triggers(
        verification_overall="PASS",
        retry_number=0,
        max_retries=2,
        proposed_transforms=[
            ProposedTransform(
                name="missing_value_policy",
                policy="fail_or_explicit_named_policy",
                reason="Missing values are present.",
            )
        ],
        analyst_uncertainty="medium",
        detective_uncertainty="medium",
        forecastability="adequate",
        already_waiting=False,
    )
    assert data == ["data_modification_proposed"]

    low = collect_checkpoint_triggers(
        verification_overall="WARN",
        retry_number=0,
        max_retries=2,
        proposed_transforms=[],
        analyst_uncertainty="high",
        detective_uncertainty="medium",
        forecastability="adequate",
        already_waiting=False,
    )
    assert "low_forecast_confidence" in low
    assert "material_uncertainty" in low

    failed = collect_checkpoint_triggers(
        verification_overall="FAIL",
        retry_number=2,
        max_retries=2,
        proposed_transforms=[],
        analyst_uncertainty="high",
        detective_uncertainty="high",
        forecastability="poor",
        already_waiting=True,
    )
    assert "verification_failed_repeatedly" in failed
    assert "low_forecast_confidence" in failed


def test_pass_without_gates_has_no_triggers() -> None:
    found = collect_checkpoint_triggers(
        verification_overall="PASS",
        retry_number=0,
        max_retries=2,
        proposed_transforms=[],
        analyst_uncertainty="medium",
        detective_uncertainty="medium",
        forecastability="adequate",
        already_waiting=False,
    )
    assert found == []


def test_proposed_transform_cannot_be_marked_applied() -> None:
    with pytest.raises(ValueError, match="must not be applied"):
        ProposedTransform(
            name="missing_value_policy",
            policy="fail_or_explicit_named_policy",
            reason="Missing values are present.",
            applied=True,
        )


def test_accept_records_approval_without_applying_transforms() -> None:
    waiting = _waiting(
        proposed_transforms=[
            ProposedTransform(
                name="missing_value_policy",
                policy="fail_or_explicit_named_policy",
                reason="Missing values are present.",
            )
        ],
        triggers=["data_modification_proposed"],
    )
    result = apply_human_checkpoint(
        waiting,
        action="accept",
        run_id="run_wait",
        retry_number=2,
        note="Proceed without silent fill.",
    )
    assert result.run_status == "completed"
    assert result.accepted is True
    assert result.review_required is False
    assert result.checkpoint.status == "approved"
    assert result.checkpoint.source_data_unmodified is True
    assert result.checkpoint.proposed_transforms[0].applied is False
    assert result.trajectory_step.agent_id == HUMAN_AGENT_ID
    assert result.trajectory_step.decision is not None
    assert result.trajectory_step.decision["action"] == "accept"
    assert result.trajectory_step.decision["transforms_applied"] is False


def test_reject_is_preserved_on_the_trajectory_step() -> None:
    result = apply_human_checkpoint(
        _waiting(),
        action="reject",
        run_id="run_wait",
        retry_number=2,
        note="Do not adopt this forecast.",
    )
    assert result.accepted is False
    assert result.checkpoint.status == "rejected"
    assert result.checkpoint.decision_note == "Do not adopt this forecast."
    assert result.trajectory_step.decision is not None
    assert result.trajectory_step.decision["action"] == "reject"
    assert result.trajectory_step.final_status == "completed"
    assert result.trajectory_step.decision["source_data_unmodified"] is True


def test_review_keeps_the_gate_open() -> None:
    result = apply_human_checkpoint(_waiting(), action="review", run_id="run_wait", retry_number=1)
    assert result.run_status == "waiting_for_approval"
    assert result.review_required is True
    assert result.checkpoint.status == "waiting_for_approval"
    assert result.trajectory_step.final_status == "waiting_for_approval"


def test_cannot_accept_when_not_waiting() -> None:
    closed = HumanCheckpoint(
        required=False,
        status="not_required",
        reason="Verification PASS.",
    )
    with pytest.raises(CheckpointDecisionError) as exc:
        apply_human_checkpoint(closed, action="accept", run_id="run_x", retry_number=0)
    assert exc.value.code == "checkpoint_not_required"


def test_cannot_decide_after_reject() -> None:
    rejected = _waiting()
    first = apply_human_checkpoint(rejected, action="reject", run_id="run_x", retry_number=0)
    with pytest.raises(CheckpointDecisionError) as exc:
        apply_human_checkpoint(
            first.checkpoint,
            action="accept",
            run_id="run_x",
            retry_number=0,
        )
    assert exc.value.code == "checkpoint_not_waiting"
