"""Explicit structured state for agents. No hidden scratchpad. No FastAPI. No yhat."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_serializer, model_validator

from app.time_utils import utc_now

AgentStatus = Literal[
    "idle",
    "running",
    "retrying",
    "completed",
    "failed",
    "waiting_for_approval",
]
ClaimKind = Literal["observation", "hypothesis"]
ClaimTopic = Literal[
    "data_quality",
    "trend",
    "seasonality",
    "anomalies",
    "structural_change",
    "forecastability",
    "investigation",
    "input",
    "strategy",
    "backtest",
    "candidates",
    "context",
    "verification",
    "report",
]
UncertaintyLevel = Literal["low", "medium", "high"]
ForecastabilityLevel = Literal["poor", "limited", "adequate", "unknown"]
JsonObject = dict[str, Any]

DATA_DETECTIVE_AGENT_ID = "data_detective"
DATA_DETECTIVE_MAX_RETRIES = 1
FORECAST_STRATEGIST_AGENT_ID = "forecast_strategist"
FORECAST_STRATEGIST_MAX_RETRIES = 1
CONTEXT_ANALYST_AGENT_ID = "context_analyst"
CONTEXT_ANALYST_MAX_RETRIES = 1
VERIFIER_AGENT_ID = "verifier"
VERIFIER_MAX_RETRIES = 1
FORECAST_ANALYST_AGENT_ID = "forecast_analyst"
FORECAST_ANALYST_MAX_RETRIES = 1
ORCHESTRATOR_AGENT_ID = "orchestrator"
ORCHESTRATOR_MAX_RETRIES = 2
HUMAN_AGENT_ID = "human"
SelectionRule = Literal["official_backtest_wis", "last_fold_wis_fallback", "none"]


def _to_utc_iso(value: datetime) -> str:
    aware = value if value.tzinfo is not None else value.replace(tzinfo=UTC)
    return aware.astimezone(UTC).isoformat().replace("+00:00", "Z")


class EvidenceItem(BaseModel):
    """One deterministic tool result, addressable by evidence_id."""

    model_config = ConfigDict(extra="forbid")

    evidence_id: str
    tool_name: str
    payload: JsonObject


class CitedClaim(BaseModel):
    """A material conclusion. Observations must cite tool evidence. Never a forecast."""

    model_config = ConfigDict(extra="forbid")

    kind: ClaimKind
    topic: ClaimTopic
    statement: str
    evidence_ids: list[str] = Field(min_length=1)
    uncertainty: UncertaintyLevel
    why_uncertainty: str


class InvestigationRecommendation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action: str
    evidence_ids: list[str] = Field(min_length=1)
    priority: Literal["high", "medium", "low"]


class ProposedTransform(BaseModel):
    """Named policy only. Must not be applied to the original series by this layer."""

    model_config = ConfigDict(extra="forbid")

    name: str
    policy: str
    reason: str
    applied: bool = False

    @model_validator(mode="after")
    def never_applied_here(self) -> ProposedTransform:
        if self.applied:
            msg = "Transforms must not be applied to source data in the checkpoint layer"
            raise ValueError(msg)
        return self


class DataDetectiveReport(BaseModel):
    """Structured Data Detective output. Does not include yhat, intervals, or scores."""

    model_config = ConfigDict(extra="forbid")

    forecastability: ForecastabilityLevel
    forecastability_rationale: str
    forecastability_evidence_ids: list[str] = Field(min_length=1)
    overall_uncertainty: UncertaintyLevel
    claims: list[CitedClaim]
    risks: list[CitedClaim]
    investigations: list[InvestigationRecommendation]
    evidence_ids_used: list[str]
    proposed_transforms: list[ProposedTransform] = Field(default_factory=list)
    modified_dataset: bool = False
    emitted_forecast: bool = False

    @model_validator(mode="after")
    def material_claims_cite_evidence_and_forbid_forecasts(self) -> DataDetectiveReport:
        if self.modified_dataset:
            msg = "Data Detective must not modify the dataset"
            raise ValueError(msg)
        if any(item.applied for item in self.proposed_transforms):
            msg = "Data Detective must not apply proposed transforms"
            raise ValueError(msg)
        if self.emitted_forecast:
            msg = "Data Detective must not emit a numerical forecast"
            raise ValueError(msg)
        for claim in (*self.claims, *self.risks):
            if not claim.evidence_ids:
                msg = "every material conclusion must reference evidence IDs"
                raise ValueError(msg)
        if not self.forecastability_evidence_ids:
            msg = "forecastability must cite evidence IDs"
            raise ValueError(msg)
        return self


class TrajectoryStep(BaseModel):
    """Append-only agent step. Retries add rows; they do not rewrite prior steps."""

    model_config = ConfigDict(extra="forbid")

    run_id: str
    agent_id: str
    timestamp: datetime
    input_state: JsonObject
    tool_requested: str | None
    tool_result: JsonObject | None
    decision: JsonObject | None
    evidence_ids: list[str]
    retry_number: int = Field(ge=0)
    final_status: AgentStatus
    case_id: str | None = None
    event_type: str | None = None
    actor: str | None = None
    payload: JsonObject | None = None
    safe_tool_arguments: JsonObject | None = None
    artifact_ref: str | None = None

    @field_serializer("timestamp")
    def serialize_timestamp(self, value: datetime) -> str:
        return _to_utc_iso(value)


class DataDetectiveState(BaseModel):
    """Explicit Data Detective state. Series values are not stored here."""

    model_config = ConfigDict(extra="forbid")

    run_id: str
    agent_id: str = DATA_DETECTIVE_AGENT_ID
    status: AgentStatus
    frequency: str | None = None
    n_observations: int | None = None
    evidence: dict[str, EvidenceItem] = Field(default_factory=dict)
    tool_errors: list[str] = Field(default_factory=list)
    report: DataDetectiveReport | None = None
    retry_number: int = 0
    trajectory: list[TrajectoryStep] = Field(default_factory=list)
    error_type: str | None = None
    error_message: str | None = None

    def append_step(self, step: TrajectoryStep) -> None:
        self.trajectory.append(step)


def new_run_id(generated_at: datetime | None = None, *, prefix: str = "data-detective") -> str:
    stamp = (generated_at if generated_at is not None else utc_now()).strftime("%Y%m%dT%H%M%SZ")
    return f"{prefix}-{stamp}"
