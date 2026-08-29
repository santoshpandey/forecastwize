"""HTTP request/response contracts. Numerical forecast fields come from domain types."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_serializer, field_validator

from app.data.schemas import ValidationIssue
from app.forecasting.base import ForecastResult
from app.services.forecast_service import BASELINE_MODEL_IDS

RunStatus = Literal[
    "queued",
    "running",
    "retrying",
    "completed",
    "failed",
    "waiting_for_approval",
]
EvaluationStatus = Literal["queued", "running", "completed", "failed"]
EvaluationSystem = Literal["baseline", "agent"]
BaselineModelId = Literal["naive", "seasonal_naive", "ets", "arima"]
CheckpointStatus = Literal["not_required", "waiting_for_approval", "approved", "rejected"]


def _to_utc_iso(value: datetime) -> str:
    aware = value if value.tzinfo is not None else value.replace(tzinfo=UTC)
    return aware.astimezone(UTC).isoformat().replace("+00:00", "Z")


class DatasetCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    filename: str = Field(min_length=1, max_length=255)
    csv_text: str = Field(min_length=1, max_length=32_000_000)


class DatasetResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    filename: str
    created_at: datetime
    n_rows: int
    n_missing_values: int
    frequency: str | None
    frequency_confidence: Literal["high", "medium", "low"] | None
    timestamp_start: datetime | None
    timestamp_end: datetime | None
    has_series_id: bool
    has_context: bool
    has_event: bool
    extra_columns: list[str]
    warnings: list[ValidationIssue] = Field(default_factory=list)
    points: list[SeriesPoint] = Field(default_factory=list)
    missing_periods: list[MissingPeriodView] = Field(default_factory=list)
    anomalies: DiagnosticSummary | None = None
    seasonality: DiagnosticSummary | None = None
    structural_break: DiagnosticSummary | None = None

    @field_serializer("created_at", "timestamp_start", "timestamp_end")
    def serialize_dt(self, value: datetime | None) -> str | None:
        if value is None:
            return None
        return _to_utc_iso(value)


class SeriesPoint(BaseModel):
    model_config = ConfigDict(extra="forbid")

    timestamp: datetime
    value: float | None

    @field_serializer("timestamp")
    def serialize_ts(self, value: datetime) -> str:
        return _to_utc_iso(value)


class MissingPeriodView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    start: datetime
    end: datetime
    n_steps: int
    series_id: str | None = None

    @field_serializer("start", "end")
    def serialize_bound(self, value: datetime) -> str:
        return _to_utc_iso(value)


class DiagnosticSummary(BaseModel):
    """Compact diagnostic copied from deterministic data tools. Not a forecast."""

    model_config = ConfigDict(extra="forbid")

    name: str
    detected: bool
    confidence: str
    strength: str
    summary: str
    n_flagged: int = 0
    limitations: list[str] = Field(default_factory=list)


class ForecastCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    dataset_id: str = Field(min_length=1)
    model_id: BaselineModelId
    horizon: int = Field(ge=1, le=366)
    frequency: str | None = None
    coverage: float = Field(default=0.95, gt=0.0, lt=1.0)
    seed: int | None = None
    seasonal_period: int | None = Field(default=None, ge=1)

    @field_validator("model_id")
    @classmethod
    def known_model(cls, value: str) -> str:
        if value not in BASELINE_MODEL_IDS:
            msg = f"model_id must be one of {list(BASELINE_MODEL_IDS)}"
            raise ValueError(msg)
        return value

    @field_validator("frequency")
    @classmethod
    def frequency_not_blank(cls, value: str | None) -> str | None:
        if value is None:
            return None
        stripped = value.strip()
        if not stripped:
            msg = "frequency must be a non-empty alias when provided"
            raise ValueError(msg)
        return stripped


class ForecastResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    dataset_id: str
    created_at: datetime
    model_id: str
    result: ForecastResult

    @field_serializer("created_at")
    def serialize_created(self, value: datetime) -> str:
        return _to_utc_iso(value)


class RunCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    dataset_id: str = Field(min_length=1)
    horizon: int = Field(ge=1, le=366)
    frequency: str | None = None
    coverage: float = Field(default=0.95, gt=0.0, lt=1.0)
    seed: int | None = None
    seasonal_period: int | None = Field(default=None, ge=1)


class ProposedTransformView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    policy: str
    reason: str
    applied: bool = False


class HumanCheckpointView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    required: bool
    status: CheckpointStatus
    reason: str
    evidence_ids: list[str] = Field(default_factory=list)
    triggers: list[str] = Field(default_factory=list)
    proposed_transforms: list[ProposedTransformView] = Field(default_factory=list)
    source_data_unmodified: bool = True
    decision_note: str | None = None


class CheckpointDecisionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action: Literal["accept", "reject", "review"]
    note: str | None = Field(default=None, max_length=2000)


class RunErrorView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    error_code: str
    message: str


class RunResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    dataset_id: str
    status: RunStatus
    created_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None
    horizon: int
    frequency: str
    coverage: float
    seed: int | None = None
    seasonal_period: int | None = None
    retry_number: int = 0
    max_retries: int = 2
    selected_strategy_id: str | None = None
    verification_overall: str | None = None
    accepted: bool = False
    review_required: bool = False
    nodes_visited: list[str] = Field(default_factory=list)
    human_checkpoint: HumanCheckpointView | None = None
    forecast: ForecastResult | None = None
    error: RunErrorView | None = None
    trajectory_available: bool = False
    candidates: list[CandidateRowView] = Field(default_factory=list)
    verification_checks: list[VerificationCheckView] = Field(default_factory=list)
    risks: list[ClaimView] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    overall_uncertainty: str | None = None
    analysis_markdown: str | None = None

    @field_serializer("created_at", "started_at", "finished_at")
    def serialize_dt(self, value: datetime | None) -> str | None:
        if value is None:
            return None
        return _to_utc_iso(value)


class CandidateRowView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    model_id: str
    official_wis: float | None
    wis_completed_only: float | None
    n_folds_planned: int
    n_folds_completed: int
    n_folds_failed: int
    rank: int | None
    error_message: str | None = None


class VerificationCheckView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    check_id: str
    name: str
    result: str
    severity: str
    explanation: str
    applicable: bool = True


class ClaimView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: str
    topic: str
    statement: str
    evidence_ids: list[str]
    uncertainty: str


class TrajectoryStepView(BaseModel):
    """Public trajectory step. Matches persisted JSONL; no stack traces."""

    model_config = ConfigDict(extra="ignore")

    run_id: str
    agent_id: str
    timestamp: datetime
    step_index: int
    agent_instruction: str
    input_state_hash: str
    input_summary: dict[str, object]
    tool_invocation: dict[str, object] | None = None
    tool_output_ref: dict[str, object] | None = None
    decision: dict[str, object] | None = None
    evidence_ids: list[str]
    retry_number: int
    status: str
    next_step: str | None = None
    error: dict[str, object] | None = None
    final_result: dict[str, object] | None = None

    @field_serializer("timestamp")
    def serialize_ts(self, value: datetime) -> str:
        return _to_utc_iso(value)


class TrajectoryResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: str
    steps: list[TrajectoryStepView]


class EvaluationCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    system: EvaluationSystem


class EvaluationCaseError(BaseModel):
    model_config = ConfigDict(extra="forbid")

    case_id: str
    error_type: str | None = None
    error_message: str | None = None


class EvaluationAggregateView(BaseModel):
    """Official aggregates copied from an evaluation artifact. Not recomputed here."""

    model_config = ConfigDict(extra="forbid")

    n_cases: int
    n_cases_completed: int
    n_cases_failed: int
    wis: float | None
    smape: float | None
    wmape: float | None
    mase: float | None
    interval_coverage: float | None
    interval_width: float | None
    human_intervention_count: int
    wis_completed_only: float | None = Field(
        description="Labeled completed-only mean. Not the headline official WIS."
    )


class EvaluationResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    status: EvaluationStatus
    system: EvaluationSystem
    created_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None
    evaluation_run_id: str | None = None
    case_list: list[str] | None = None
    aggregate: EvaluationAggregateView | None = None
    errors: list[EvaluationCaseError] = Field(default_factory=list)
    error: RunErrorView | None = None

    @field_serializer("created_at", "started_at", "finished_at")
    def serialize_dt(self, value: datetime | None) -> str | None:
        if value is None:
            return None
        return _to_utc_iso(value)


class EvaluationCompareRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    baseline_id: str = Field(min_length=1)
    agent_id: str = Field(min_length=1)


class MetricComparisonView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    direction: str
    baseline: float | None
    agent: float | None
    delta_agent_minus_baseline: float | None
    relative_improvement: float | None


class EvaluationCompareResponse(BaseModel):
    """Comparison copied from evaluation.compare. The UI must not recompute WIS."""

    model_config = ConfigDict(extra="forbid")

    comparison_id: str
    baseline_evaluation_run_id: str
    agent_evaluation_run_id: str
    case_list: list[str]
    case_lists_identical: bool
    primary_metric: str
    aggregate: dict[str, MetricComparisonView]
    n_cases_failed: MetricComparisonView
    human_intervention_count: MetricComparisonView
    notes: list[str]
    errors: dict[str, list[EvaluationCaseError]]


class CaseComparisonView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    case_id: str
    baseline_status: str
    agent_status: str
    baseline_error_type: str | None
    agent_error_type: str | None
    baseline_error_message: str | None
    agent_error_message: str | None
    review_required: bool
    retry_number: int
    metrics: dict[str, MetricComparisonView]
    runtime_seconds: MetricComparisonView


class AggregateComparisonView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    n_cases: int
    metrics: dict[str, MetricComparisonView]
    n_cases_failed: MetricComparisonView
    human_intervention_count: MetricComparisonView
    wall_seconds: MetricComparisonView
    cases_seconds: MetricComparisonView


class ComparisonArtifactView(BaseModel):
    """Full comparison.json payload. Values are copied, not recomputed."""

    model_config = ConfigDict(extra="forbid")

    comparison_id: str
    timestamp: str
    git_commit: str | None
    baseline_evaluation_run_id: str
    agent_evaluation_run_id: str
    case_list: list[str]
    case_lists_identical: bool
    primary_metric: str
    per_case: list[CaseComparisonView]
    aggregate: AggregateComparisonView
    errors: dict[str, list[EvaluationCaseError]]
    notes: list[str]


class CatalogCaseView(BaseModel):
    model_config = ConfigDict(extra="forbid")

    case_id: str
    name: str
    expected_challenge: str
    description: str
    challenging: bool


class EvaluationDashboardResponse(BaseModel):
    """Official evaluation artifacts for the dashboard. The UI must not recompute WIS."""

    model_config = ConfigDict(extra="forbid")

    artifact_path: str
    baseline_artifact_path: str | None = None
    agent_artifact_path: str | None = None
    changelog_path: str
    comparison: ComparisonArtifactView
    catalog: list[CatalogCaseView]


class ChangelogDocumentResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    path: str
    markdown: str
