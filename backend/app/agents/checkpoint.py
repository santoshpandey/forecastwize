"""Human checkpoint decisions. No FastAPI. No source-data mutation. No yhat."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.agents.state import (
    HUMAN_AGENT_ID,
    ORCHESTRATOR_AGENT_ID,
    AgentStatus,
    ProposedTransform,
    TrajectoryStep,
)
from app.time_utils import utc_now

CheckpointAction = Literal["accept", "reject", "review"]
CheckpointStatus = Literal["not_required", "waiting_for_approval", "approved", "rejected"]
CheckpointTrigger = Literal[
    "data_modification_proposed",
    "low_forecast_confidence",
    "verification_failed_repeatedly",
    "material_uncertainty",
]
RunStatusAfterDecision = Literal["waiting_for_approval", "completed"]

TRIGGER_REASONS: dict[CheckpointTrigger, str] = {
    "data_modification_proposed": (
        "A data modification was proposed. Source data is not modified automatically."
    ),
    "low_forecast_confidence": "Forecast confidence is low.",
    "verification_failed_repeatedly": "Verification failed repeatedly (retries exhausted).",
    "material_uncertainty": "Material uncertainty remains.",
}


class HumanCheckpoint(BaseModel):
    """Explicit human gate. The graph never auto-approves."""

    model_config = ConfigDict(extra="forbid")

    required: bool
    status: CheckpointStatus
    reason: str
    evidence_ids: list[str] = Field(default_factory=list)
    triggers: list[CheckpointTrigger] = Field(default_factory=list)
    proposed_transforms: list[ProposedTransform] = Field(default_factory=list)
    source_data_unmodified: bool = True
    decision_note: str | None = None
    checkpoint_id: str | None = None


class CheckpointDecisionError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


class CheckpointDecision(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action: CheckpointAction
    run_status: RunStatusAfterDecision
    accepted: bool
    review_required: bool
    checkpoint: HumanCheckpoint
    trajectory_step: TrajectoryStep
    continuation_step: TrajectoryStep | None = None


def collect_checkpoint_triggers(
    *,
    verification_overall: str | None,
    retry_number: int,
    max_retries: int,
    proposed_transforms: list[ProposedTransform],
    analyst_uncertainty: str | None,
    detective_uncertainty: str | None,
    forecastability: str | None,
    already_waiting: bool,
) -> list[CheckpointTrigger]:
    """Return why a human gate is required. Does not mutate data or invent scores."""
    found: list[CheckpointTrigger] = []
    if any(not item.applied for item in proposed_transforms):
        found.append("data_modification_proposed")
    if verification_overall == "WARN":
        found.append("low_forecast_confidence")
        found.append("material_uncertainty")
    failed_repeatedly = verification_overall == "FAIL" and (
        already_waiting or retry_number >= max_retries
    )
    if failed_repeatedly:
        found.append("verification_failed_repeatedly")
    if analyst_uncertainty == "high" and "material_uncertainty" not in found:
        found.append("material_uncertainty")
    poor = forecastability == "poor"
    if detective_uncertainty == "high" and poor and "low_forecast_confidence" not in found:
        found.append("low_forecast_confidence")
    ordered: list[CheckpointTrigger] = []
    for item in (
        "data_modification_proposed",
        "low_forecast_confidence",
        "verification_failed_repeatedly",
        "material_uncertainty",
    ):
        if item in found:
            ordered.append(item)
    return ordered


def reason_for_triggers(triggers: list[CheckpointTrigger]) -> str:
    if not triggers:
        return "Human review is required."
    return " ".join(TRIGGER_REASONS[item] for item in triggers)


def new_checkpoint_id(run_id: str) -> str:
    """Stable id for the single human gate on a run. Not a secret."""
    return f"ckpt-{run_id}"


def apply_human_checkpoint(
    checkpoint: HumanCheckpoint | None,
    *,
    action: CheckpointAction,
    run_id: str,
    retry_number: int,
    note: str | None = None,
    evidence_ids: list[str] | None = None,
    case_id: str | None = None,
) -> CheckpointDecision:
    """Record Accept / Reject / Review. Never modifies source data."""
    if checkpoint is None or not checkpoint.required:
        raise CheckpointDecisionError(
            "checkpoint_not_required",
            "No human checkpoint is waiting on this run.",
        )
    if checkpoint.status != "waiting_for_approval":
        raise CheckpointDecisionError(
            "checkpoint_not_waiting",
            f"Checkpoint status is {checkpoint.status}; Accept/Reject/Review are not open.",
        )
    eids = list(evidence_ids if evidence_ids is not None else checkpoint.evidence_ids)
    transforms = [
        item.model_copy(update={"applied": False}) for item in checkpoint.proposed_transforms
    ]
    trimmed = None if note is None else note.strip() or None
    ckpt_id = checkpoint.checkpoint_id or new_checkpoint_id(run_id)
    if action == "review":
        next_checkpoint = checkpoint.model_copy(
            update={
                "status": "waiting_for_approval",
                "decision_note": trimmed,
                "source_data_unmodified": True,
                "proposed_transforms": transforms,
                "checkpoint_id": ckpt_id,
            }
        )
        run_status: RunStatusAfterDecision = "waiting_for_approval"
        accepted = False
        review_required = True
        traj_status: AgentStatus = "waiting_for_approval"
    elif action == "accept":
        next_checkpoint = checkpoint.model_copy(
            update={
                "status": "approved",
                "decision_note": trimmed,
                "source_data_unmodified": True,
                "proposed_transforms": transforms,
                "checkpoint_id": ckpt_id,
            }
        )
        run_status = "completed"
        accepted = True
        review_required = False
        traj_status = "completed"
    else:
        next_checkpoint = checkpoint.model_copy(
            update={
                "status": "rejected",
                "decision_note": trimmed,
                "source_data_unmodified": True,
                "proposed_transforms": transforms,
                "checkpoint_id": ckpt_id,
            }
        )
        run_status = "completed"
        accepted = False
        review_required = False
        traj_status = "completed"
    decision = {
        "action": action,
        "actor": HUMAN_AGENT_ID,
        "source_data_unmodified": True,
        "transforms_applied": False,
        "note": trimmed,
        "triggers": list(next_checkpoint.triggers),
        "checkpoint_status": next_checkpoint.status,
        "checkpoint_id": ckpt_id,
    }
    step = TrajectoryStep(
        run_id=run_id,
        agent_id=HUMAN_AGENT_ID,
        timestamp=utc_now(),
        input_state={
            "node": "HUMAN_CHECKPOINT",
            "prior_status": checkpoint.status,
            "note": "source data is not modified",
        },
        tool_requested=None,
        tool_result=None,
        decision=decision,
        evidence_ids=eids,
        retry_number=retry_number,
        final_status=traj_status,
        event_type="HUMAN_DECISION",
        actor=HUMAN_AGENT_ID,
        case_id=case_id,
        payload=_human_decision_payload(
            checkpoint_id=ckpt_id,
            action=action,
            checkpoint_status=next_checkpoint.status,
            note=trimmed,
        ),
    )
    return CheckpointDecision(
        action=action,
        run_status=run_status,
        accepted=accepted,
        review_required=review_required,
        checkpoint=next_checkpoint,
        trajectory_step=step,
        continuation_step=_workflow_continuation_step(
            run_id=run_id,
            action=action,
            checkpoint_id=ckpt_id,
            retry_number=retry_number,
            case_id=case_id,
            evidence_ids=eids,
            accepted=accepted,
        ),
    )


def _human_decision_payload(
    *,
    checkpoint_id: str,
    action: CheckpointAction,
    checkpoint_status: CheckpointStatus,
    note: str | None,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "checkpoint_id": checkpoint_id,
        "decision": action,
        "checkpoint_status": checkpoint_status,
        "source_data_unmodified": True,
        "actor": HUMAN_AGENT_ID,
    }
    if note is not None:
        payload["note"] = note
    return payload


def _workflow_continuation_step(
    *,
    run_id: str,
    action: CheckpointAction,
    checkpoint_id: str,
    retry_number: int,
    case_id: str | None,
    evidence_ids: list[str],
    accepted: bool,
) -> TrajectoryStep | None:
    """Accept/Reject complete the run. Review leaves the gate open."""
    if action == "review":
        return None
    return TrajectoryStep(
        run_id=run_id,
        agent_id=ORCHESTRATOR_AGENT_ID,
        timestamp=utc_now(),
        input_state={
            "node": "FINALIZE",
            "prior_event": "HUMAN_DECISION",
            "note": "workflow continuation after human decision",
        },
        tool_requested=None,
        tool_result=None,
        decision={
            "status": "completed",
            "review_required": False,
            "continuation_of": "HUMAN_DECISION",
            "action": action,
        },
        evidence_ids=list(evidence_ids),
        retry_number=retry_number,
        final_status="completed",
        event_type="RUN_COMPLETED",
        actor=ORCHESTRATOR_AGENT_ID,
        case_id=case_id,
        payload={
            "final_status": "completed",
            "continuation_of": "HUMAN_DECISION",
            "decision": action,
            "checkpoint_id": checkpoint_id,
            "accepted": accepted,
        },
    )
