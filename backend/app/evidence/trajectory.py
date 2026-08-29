"""Typed trajectory records. Append-only JSON. No FastAPI. No LLM. No yhat invention."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_serializer, model_validator

JsonObject = dict[str, Any]
TrajectoryStatus = Literal[
    "idle",
    "running",
    "retrying",
    "completed",
    "failed",
    "waiting_for_approval",
]

AGENT_INSTRUCTIONS: dict[str, str] = {
    "data_detective": (
        "Inspect diagnostics only. Cite evidence IDs. Do not emit yhat or modify the series."
    ),
    "forecast_strategist": (
        "Propose candidates as hypotheses. Recommend strategy_id only from official backtest WIS."
    ),
    "context_analyst": (
        "Record observed context facts. Do not infer causality or adjust forecasts."
    ),
    "verifier": "Challenge the forecast with deterministic checks. Do not emit or adjust yhat.",
    "forecast_analyst": (
        "Write an evidence-cited narrative from supplied artifacts. "
        "Do not invent numbers or events."
    ),
    "orchestrator": (
        "Run PROFILE → DIAGNOSE → CONTEXT → STRATEGY → BACKTEST → FORECAST → VERIFY → "
        "RETRY_OR_ACCEPT → ANALYZE → FINALIZE. Verification is required before accept. "
        "Retries are capped at 2."
    ),
    "human": (
        "Record Accept, Reject, or Review on an explicit checkpoint. "
        "Do not modify source data. Do not invent yhat."
    ),
}

REQUIRED_TRAJECTORY_FIELDS: tuple[str, ...] = (
    "run_id",
    "agent_id",
    "timestamp",
    "input_state_hash",
    "input_summary",
    "tool_invocation",
    "tool_output_ref",
    "decision",
    "evidence_ids",
    "retry_number",
    "status",
    "error",
    "agent_instruction",
    "next_step",
    "final_result",
)

REVIEWER_SEQUENCE: tuple[str, ...] = (
    "agent_instruction",
    "input_summary",
    "tool_invocation",
    "tool_output_ref",
    "decision",
    "next_step",
    "final_result",
)


def _to_utc_iso(value: datetime) -> str:
    aware = value if value.tzinfo is not None else value.replace(tzinfo=UTC)
    return aware.astimezone(UTC).isoformat().replace("+00:00", "Z")


class ToolInvocation(BaseModel):
    """Approved tool call. Arguments are summaries, never raw series or secrets."""

    model_config = ConfigDict(extra="forbid")

    tool_name: str
    arguments_summary: JsonObject = Field(default_factory=dict)


class ToolOutputRef(BaseModel):
    """Pointer to a persisted tool payload. The JSONL line does not embed the payload."""

    model_config = ConfigDict(extra="forbid")

    artifact_id: str
    sha256: str
    kind: str = "tool_output"
    ok: bool | None = None


class TrajectoryError(BaseModel):
    """Public error on a step. No stack traces. Secrets must already be redacted."""

    model_config = ConfigDict(extra="forbid")

    error_type: str
    error_message: str


class TrajectoryRecord(BaseModel):
    """One append-only agent step. Retries add rows; they do not rewrite prior steps."""

    model_config = ConfigDict(extra="forbid")

    run_id: str
    agent_id: str
    timestamp: datetime
    step_index: int = Field(ge=0)
    agent_instruction: str = Field(min_length=1)
    input_state_hash: str = Field(min_length=16)
    input_summary: JsonObject
    tool_invocation: ToolInvocation | None = None
    tool_output_ref: ToolOutputRef | None = None
    decision: JsonObject | None = None
    evidence_ids: list[str]
    retry_number: int = Field(ge=0)
    status: TrajectoryStatus
    next_step: str | None = None
    error: TrajectoryError | None = None
    final_result: JsonObject | None = None
    input_state: JsonObject
    tool_requested: str | None = None
    tool_result: JsonObject | None = None
    final_status: TrajectoryStatus

    @field_serializer("timestamp")
    def serialize_timestamp(self, value: datetime) -> str:
        return _to_utc_iso(value)

    @model_validator(mode="after")
    def status_aliases_match_and_errors_are_visible(self) -> TrajectoryRecord:
        if self.final_status != self.status:
            msg = "final_status must equal status"
            raise ValueError(msg)
        if self.status == "failed" and self.error is None:
            msg = "failed steps must include error information"
            raise ValueError(msg)
        if self.tool_requested is None and self.tool_invocation is not None:
            object.__setattr__(self, "tool_requested", self.tool_invocation.tool_name)
        if self.tool_invocation is None and self.tool_requested is not None:
            object.__setattr__(
                self,
                "tool_invocation",
                ToolInvocation(tool_name=self.tool_requested, arguments_summary={}),
            )
        return self


def instruction_for(agent_id: str, *, node: str | None = None) -> str:
    base = AGENT_INSTRUCTIONS.get(
        agent_id, f"Agent {agent_id}: record evidence; do not invent yhat."
    )
    if node:
        return f"{base} Current node: {node}."
    return base


def reviewer_walk(records: list[TrajectoryRecord]) -> list[JsonObject]:
    """Project records into the reviewer sequence: instruction → … → final result."""
    walk: list[JsonObject] = []
    for record in records:
        walk.append({key: getattr(record, key) for key in REVIEWER_SEQUENCE})
    return walk
