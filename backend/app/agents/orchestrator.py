"""ForecastWize orchestrator: explicit typed state machine for the forecast workflow.

Nodes: START → PROFILE → DIAGNOSE → CONTEXT → STRATEGY → BACKTEST → FORECAST →
VERIFY → RETRY_OR_ACCEPT → ANALYZE → FINALIZE.

Equivalent explicit state machine: typed state, not a hidden loop.
No FastAPI. No LLM. No unbounded retries. Verification is required before an
accepted result. Deterministic tools produce numbers; this graph records decisions
and evidence IDs.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

import numpy as np
import pandas as pd
from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.agents.analyst import ForecastAnalystReport, ForecastAnalystState, run_forecast_analyst
from app.agents.checkpoint import (
    HumanCheckpoint,
    ProposedTransform,
    collect_checkpoint_triggers,
    new_checkpoint_id,
    reason_for_triggers,
)
from app.agents.context_analyst import (
    ContextAnalystReport,
    ContextAnalystState,
    run_context_analyst,
)
from app.agents.data_detective import DataDetectiveState, run_data_detective
from app.agents.forecast_strategist import (
    BusinessContext,
    DatasetDiagnostics,
    ForecastStrategistReport,
    ForecastStrategistState,
    propose_candidate_ids,
    run_forecast_strategist,
)
from app.agents.state import (
    ORCHESTRATOR_AGENT_ID,
    ORCHESTRATOR_MAX_RETRIES,
    AgentStatus,
    DataDetectiveReport,
    EvidenceItem,
    TrajectoryStep,
    new_run_id,
)
from app.agents.verifier import VerifierReport, VerifierState, run_verifier
from app.data.seasonality import period_from_frequency
from app.evidence.logger import persist_trajectory_step, resolve_trajectory_path
from app.forecasting.backtesting import DEFAULT_ORIGIN_PLANNING, OriginPlanning
from app.forecasting.base import ForecastResult
from app.forecasting.robustness import DEFAULT_SELECTION_POLICY, SelectionPolicy
from app.services.forecast_service import BASELINE_MODEL_IDS, run_baseline_forecast
from app.time_utils import utc_now
from app.tools.data_tools import INSPECT_SERIES, DataToolEnvelope, DataToolSpec, run_named_data_tool
from app.tools.verification_tools import ForecastSnapshot

JsonObject = dict[str, Any]
WorkflowNode = Literal[
    "START",
    "PROFILE",
    "DIAGNOSE",
    "CONTEXT",
    "STRATEGY",
    "BACKTEST",
    "FORECAST",
    "VERIFY",
    "RETRY_OR_ACCEPT",
    "ANALYZE",
    "FINALIZE",
]
CheckpointStatus = Literal["not_required", "waiting_for_approval", "approved", "rejected"]
OrchestratorStatus = Literal[
    "running",
    "retrying",
    "completed",
    "failed",
    "waiting_for_approval",
]

MAX_GRAPH_STEPS = 40
_REPO_ROOT = Path(__file__).resolve().parents[3]
_TRAJECTORIES_DIR = _REPO_ROOT / "trajectories"

NODE_ORDER: tuple[WorkflowNode, ...] = (
    "START",
    "PROFILE",
    "DIAGNOSE",
    "CONTEXT",
    "STRATEGY",
    "BACKTEST",
    "FORECAST",
    "VERIFY",
    "RETRY_OR_ACCEPT",
    "ANALYZE",
    "FINALIZE",
)


class NodeFailure(BaseModel):
    """Preserved node failure. Retries do not delete prior failures."""

    model_config = ConfigDict(extra="forbid")

    node: WorkflowNode
    error_type: str
    error_message: str
    retry_number: int
    evidence_ids: list[str] = Field(default_factory=list)


class OrchestratorState(BaseModel):
    """Explicit graph state. Raw series values are not stored here."""

    model_config = ConfigDict(extra="forbid")

    run_id: str
    agent_id: str = ORCHESTRATOR_AGENT_ID
    status: OrchestratorStatus
    node: WorkflowNode
    nodes_visited: list[WorkflowNode] = Field(default_factory=list)
    retry_number: int = Field(default=0, ge=0, le=ORCHESTRATOR_MAX_RETRIES)
    max_retries: int = ORCHESTRATOR_MAX_RETRIES
    frequency: str | None = None
    horizon: int | None = None
    n_observations: int | None = None
    proposed_candidate_ids: list[str] = Field(default_factory=list)
    selected_strategy_id: str | None = None
    tried_strategy_ids: list[str] = Field(default_factory=list)
    backtest_executed: bool = False
    verification_ran: bool = False
    verification_overall: str | None = None
    review_required: bool = False
    accepted: bool = False
    human_checkpoint: HumanCheckpoint | None = None
    proposed_transforms: list[ProposedTransform] = Field(default_factory=list)
    evidence: dict[str, EvidenceItem] = Field(default_factory=dict)
    failures: list[NodeFailure] = Field(default_factory=list)
    detective_report: DataDetectiveReport | None = None
    context_report: ContextAnalystReport | None = None
    strategist_report: ForecastStrategistReport | None = None
    verifier_report: VerifierReport | None = None
    analyst_report: ForecastAnalystReport | None = None
    forecast: ForecastResult | ForecastSnapshot | None = None
    diagnostics: DatasetDiagnostics | None = None
    trajectory: list[TrajectoryStep] = Field(default_factory=list)
    error_type: str | None = None
    error_message: str | None = None
    case_id: str | None = None

    def append_step(self, step: TrajectoryStep) -> None:
        self.trajectory.append(step)

    @model_validator(mode="after")
    def retries_are_bounded(self) -> OrchestratorState:
        if self.retry_number > self.max_retries:
            msg = "retry_number exceeds orchestrator cap"
            raise ValueError(msg)
        if self.max_retries != ORCHESTRATOR_MAX_RETRIES:
            msg = "orchestrator max retries must remain 2"
            raise ValueError(msg)
        return self


@dataclass
class OrchestratorHooks:
    """Optional replacements for node work. None means call the real deterministic path."""

    profile: Callable[..., DataToolEnvelope] | None = None
    diagnose: Callable[..., DataDetectiveState] | None = None
    context: Callable[..., ContextAnalystState] | None = None
    strategy: Callable[..., list[str]] | None = None
    backtest: Callable[..., ForecastStrategistState] | None = None
    forecast: Callable[..., ForecastResult | ForecastSnapshot] | None = None
    verify: Callable[..., VerifierState] | None = None
    analyze: Callable[..., ForecastAnalystState] | None = None


def run_orchestrator(
    timestamps: pd.Series | pd.DatetimeIndex | None,
    values: pd.Series | np.ndarray | None,
    *,
    horizon: int,
    frequency: str,
    event_labels: pd.Series | list[object] | None = None,
    context_labels: pd.Series | list[object] | None = None,
    candidate_model_ids: tuple[str, ...] | None = None,
    seasonal_period: int | None = None,
    seed: int | None = None,
    coverage: float = 0.95,
    hooks: OrchestratorHooks | None = None,
    run_id: str | None = None,
    generated_at: datetime | None = None,
    trajectory_path: Path | None = None,
    persist_trajectory: bool = True,
    origin_planning: OriginPlanning = DEFAULT_ORIGIN_PLANNING,
    selection_policy: SelectionPolicy = DEFAULT_SELECTION_POLICY,
    case_id: str | None = None,
    evaluation_metadata: dict[str, Any] | None = None,
) -> OrchestratorState:
    """Run the explicit forecast graph. Verification cannot be skipped.

    Retries are capped at 2. Failures stay in `failures`. Series arrays are not
    copied into graph state. Official default is ``selection_policy='exp010'``
    (promoted EXP-010). Pass ``selection_policy='default'`` plus
    ``origin_planning='model_specific'`` to reproduce EXP-009.
    """
    created = generated_at if generated_at is not None else utc_now()
    rid = run_id if run_id is not None else new_run_id(created, prefix="orchestrator")
    state = OrchestratorState(
        run_id=rid,
        status="running",
        node="START",
        frequency=frequency,
        horizon=horizon,
        n_observations=None if values is None else int(np.asarray(values).size),
        retry_number=0,
        max_retries=ORCHESTRATOR_MAX_RETRIES,
        case_id=case_id,
    )
    out_path = resolve_trajectory_path(
        persist=persist_trajectory,
        path=trajectory_path,
        run_id=rid,
        default_dir=_TRAJECTORIES_DIR,
        truncate=True,
    )

    period = seasonal_period if seasonal_period is not None else period_from_frequency(frequency)
    ctx = _Runtime(
        timestamps=timestamps,
        values=values,
        event_labels=event_labels,
        context_labels=context_labels,
        horizon=horizon,
        frequency=frequency,
        seasonal_period=period,
        seed=seed,
        coverage=coverage,
        candidate_model_ids=candidate_model_ids,
        origin_planning=origin_planning,
        selection_policy=selection_policy,
        generated_at=created,
        hooks=hooks if hooks is not None else OrchestratorHooks(),
        path=out_path,
        next_id=_evidence_id_factory(),
        case_id=case_id,
        persist_children=out_path is not None,
        evaluation_metadata=dict(evaluation_metadata) if evaluation_metadata else {},
    )
    _record(
        state,
        ctx,
        tool_requested=None,
        evidence_ids=[],
        decision={"event": "RUN_STARTED"},
        status="running",
        event_type="RUN_STARTED",
        payload={
            "run_id": state.run_id,
            "case_id": case_id,
            "selection_policy": selection_policy,
            "origin_planning": origin_planning,
            "frequency": frequency,
            "horizon": horizon,
            **ctx.evaluation_metadata,
        },
    )
    steps = 0
    while state.node != "FINALIZE" and steps < MAX_GRAPH_STEPS:
        steps += 1
        current = state.node
        state.nodes_visited.append(current)
        if current == "START":
            _node_start(state, ctx)
        elif current == "PROFILE":
            _node_profile(state, ctx)
        elif current == "DIAGNOSE":
            _node_diagnose(state, ctx)
        elif current == "CONTEXT":
            _node_context(state, ctx)
        elif current == "STRATEGY":
            _node_strategy(state, ctx)
        elif current == "BACKTEST":
            _node_backtest(state, ctx)
        elif current == "FORECAST":
            _node_forecast(state, ctx)
        elif current == "VERIFY":
            _node_verify(state, ctx)
        elif current == "RETRY_OR_ACCEPT":
            _node_retry_or_accept(state, ctx)
        elif current == "ANALYZE":
            _node_analyze(state, ctx)
        else:
            _halt(state, ctx, "UnknownNode", f"Unknown node {current}")
            break
        if state.node == current and current != "FINALIZE":
            _halt(state, ctx, "StalledGraph", f"Node {current} did not transition")
            break
    if state.node != "FINALIZE":
        _halt(state, ctx, "StepCapExceeded", "Graph step cap reached; loop is not permitted")
    _node_finalize(state, ctx)
    return state


@dataclass
class _Runtime:
    timestamps: pd.Series | pd.DatetimeIndex | None
    values: pd.Series | np.ndarray | None
    event_labels: pd.Series | list[object] | None
    context_labels: pd.Series | list[object] | None
    horizon: int
    frequency: str
    seasonal_period: int | None
    seed: int | None
    coverage: float
    candidate_model_ids: tuple[str, ...] | None
    origin_planning: OriginPlanning
    selection_policy: SelectionPolicy
    generated_at: datetime
    hooks: OrchestratorHooks
    path: Path | None
    next_id: Callable[[], str]
    case_id: str | None
    persist_children: bool
    evaluation_metadata: JsonObject


def _node_start(state: OrchestratorState, ctx: _Runtime) -> None:
    eid = _store(
        state,
        ctx,
        "graph_start",
        {"node": "START", "max_retries": ORCHESTRATOR_MAX_RETRIES},
    )
    _record(
        state,
        ctx,
        tool_requested=None,
        evidence_ids=[eid],
        decision={"next": "PROFILE"},
        status="running",
    )
    state.node = "PROFILE"


def _node_profile(state: OrchestratorState, ctx: _Runtime) -> None:
    spec = DataToolSpec(frequency=ctx.frequency, seasonal_period=ctx.seasonal_period)
    if ctx.hooks.profile is not None:
        envelope = ctx.hooks.profile(timestamps=ctx.timestamps, values=ctx.values, spec=spec)
    else:
        envelope = run_named_data_tool(INSPECT_SERIES, ctx.timestamps, ctx.values, spec)
    eid = _store(state, ctx, envelope.tool_name, dict(envelope.payload))
    _record(
        state,
        ctx,
        tool_requested=INSPECT_SERIES,
        evidence_ids=[eid],
        tool_result={"ok": envelope.ok, "error_type": envelope.error_type},
        decision={"ok": envelope.ok},
        status="running",
    )
    if not envelope.ok:
        _fail_node(
            state,
            ctx,
            "PROFILE",
            envelope.error_type or "ProfileFailed",
            envelope.error_message or "inspect_series failed",
            [eid],
        )
        return
    inferred = envelope.payload.get("frequency")
    if state.frequency is None and isinstance(inferred, str):
        state.frequency = inferred
    n_rows = envelope.payload.get("n_rows")
    if isinstance(n_rows, int):
        state.n_observations = n_rows
    state.node = "DIAGNOSE"


def _node_diagnose(state: OrchestratorState, ctx: _Runtime) -> None:
    if ctx.hooks.diagnose is not None:
        det = ctx.hooks.diagnose(
            timestamps=ctx.timestamps,
            values=ctx.values,
            frequency=ctx.frequency,
            seasonal_period=ctx.seasonal_period,
        )
    else:
        det = run_data_detective(
            ctx.timestamps,
            ctx.values,
            frequency=ctx.frequency,
            seasonal_period=ctx.seasonal_period,
            generated_at=ctx.generated_at,
            run_id=state.run_id,
            trajectory_path=ctx.path,
            persist_trajectory=ctx.persist_children,
            case_id=ctx.case_id,
            append_to_trajectory=True,
        )
    eids = _ingest(state, ctx, "diagnose", det.evidence)
    if det.report is not None:
        state.detective_report = det.report
        state.proposed_transforms = [item.model_copy() for item in det.report.proposed_transforms]
    state.diagnostics = _diagnostics_from_detective(det, state.frequency)
    diag_eid = _store(state, ctx, "diagnostics_input", state.diagnostics.model_dump(mode="json"))
    eids.append(diag_eid)
    _record(
        state,
        ctx,
        tool_requested="run_data_detective",
        evidence_ids=eids,
        decision={"status": det.status},
        status="running",
        event_type="AGENT_COMPLETED",
        actor="data_detective",
        payload={"status": det.status},
    )
    if det.status == "failed":
        _fail_node(
            state,
            ctx,
            "DIAGNOSE",
            det.error_type or "DiagnoseFailed",
            det.error_message or "Data Detective failed",
            eids,
        )
        return
    state.node = "CONTEXT"


def _node_context(state: OrchestratorState, ctx: _Runtime) -> None:
    if ctx.hooks.context is not None:
        ctx_state = ctx.hooks.context(
            timestamps=ctx.timestamps,
            event_labels=ctx.event_labels,
            context_labels=ctx.context_labels,
        )
    else:
        ctx_state = run_context_analyst(
            timestamps=ctx.timestamps,
            event_labels=ctx.event_labels,
            context_labels=ctx.context_labels,
            generated_at=ctx.generated_at,
            run_id=state.run_id,
            trajectory_path=ctx.path,
            persist_trajectory=ctx.persist_children,
            case_id=ctx.case_id,
            append_to_trajectory=True,
        )
    eids = _ingest(state, ctx, "context", ctx_state.evidence)
    if ctx_state.report is not None:
        state.context_report = ctx_state.report
    _record(
        state,
        ctx,
        tool_requested="inspect_context",
        evidence_ids=eids,
        decision={"context_available": ctx_state.context_available},
        status="running",
        event_type="AGENT_COMPLETED",
        actor="context_analyst",
        payload={"context_available": ctx_state.context_available},
    )
    if ctx_state.status == "failed":
        _fail_node(
            state,
            ctx,
            "CONTEXT",
            ctx_state.error_type or "ContextFailed",
            ctx_state.error_message or "Context Analyst failed",
            eids,
        )
        return
    state.node = "STRATEGY"


def _node_strategy(state: OrchestratorState, ctx: _Runtime) -> None:
    if state.diagnostics is None:
        _fail_node(state, ctx, "STRATEGY", "MissingDiagnostics", "No diagnostics for strategy", [])
        return
    if ctx.hooks.strategy is not None:
        proposed = list(ctx.hooks.strategy(state.diagnostics))
    else:
        proposed = propose_candidate_ids(state.diagnostics)
    if ctx.candidate_model_ids is not None:
        allow = list(ctx.candidate_model_ids)
        filtered = [item for item in proposed if item in allow]
        proposed = filtered if filtered else allow
    state.proposed_candidate_ids = list(proposed)
    eid = _store(
        state,
        ctx,
        "propose_candidates",
        {"candidate_ids": state.proposed_candidate_ids, "hypothesis_only": True},
    )
    _record(
        state,
        ctx,
        tool_requested=None,
        evidence_ids=[eid],
        decision={
            "proposed_candidate_ids": state.proposed_candidate_ids,
            "note": "Shortlist is a hypothesis, not a superiority claim.",
        },
        status="running",
    )
    state.node = "BACKTEST"


def _node_backtest(state: OrchestratorState, ctx: _Runtime) -> None:
    context_meta = None
    if state.context_report is not None:
        context_meta = BusinessContext(
            has_event_column=state.context_report.context_available,
            n_event_non_null=len(state.context_report.observed_facts),
        )
    ids = _backtest_model_ids(ctx)
    if ctx.hooks.backtest is not None:
        strat = ctx.hooks.backtest(
            timestamps=ctx.timestamps,
            values=ctx.values,
            horizon=ctx.horizon,
            frequency=ctx.frequency,
            diagnostics=state.diagnostics,
            candidate_model_ids=ids,
        )
    else:
        strat = run_forecast_strategist(
            ctx.timestamps,
            ctx.values,
            horizon=ctx.horizon,
            frequency=ctx.frequency,
            diagnostics=state.diagnostics,
            context=context_meta,
            candidate_model_ids=ids,
            seasonal_period=ctx.seasonal_period,
            seed=ctx.seed,
            generated_at=ctx.generated_at,
            run_id=state.run_id,
            trajectory_path=ctx.path,
            persist_trajectory=ctx.persist_children,
            origin_planning=ctx.origin_planning,
            selection_policy=ctx.selection_policy,
            case_id=ctx.case_id,
            append_to_trajectory=True,
        )
    eids = _ingest(state, ctx, "backtest", strat.evidence)
    if strat.report is not None:
        state.strategist_report = strat.report
        state.backtest_executed = strat.report.backtest_executed
        state.selected_strategy_id = strat.report.recommended_strategy_id
    _record(
        state,
        ctx,
        tool_requested="evaluate_candidates",
        evidence_ids=eids,
        decision={
            "recommended_strategy_id": state.selected_strategy_id,
            "backtest_executed": state.backtest_executed,
            "hypothesis_candidate_ids": list(state.proposed_candidate_ids),
            "backtest_candidate_ids": list(ids),
        },
        status="running",
        event_type="AGENT_COMPLETED",
        actor="forecast_strategist",
        payload={
            "recommended_strategy_id": state.selected_strategy_id,
            "backtest_executed": state.backtest_executed,
            "selection_policy": ctx.selection_policy,
        },
    )
    if strat.status == "failed" or not state.backtest_executed:
        _fail_node(
            state,
            ctx,
            "BACKTEST",
            strat.error_type or "BacktestFailed",
            strat.error_message or "Backtest did not produce an official ranking",
            eids,
        )
        return
    if state.selected_strategy_id is None:
        state.selected_strategy_id = _first_ranked(state.strategist_report)
    if state.selected_strategy_id is None:
        _fail_node(
            state,
            ctx,
            "BACKTEST",
            "NoStrategy",
            "No strategy_id is available after backtesting",
            eids,
        )
        return
    state.node = "FORECAST"


def _node_forecast(state: OrchestratorState, ctx: _Runtime) -> None:
    model_id = state.selected_strategy_id
    if model_id is None:
        _fail_node(state, ctx, "FORECAST", "NoStrategy", "Cannot forecast without strategy_id", [])
        return
    forecast_event = "RETRY_STARTED" if state.status == "retrying" else "FORECAST_STARTED"
    _record(
        state,
        ctx,
        tool_requested=None,
        evidence_ids=[],
        decision={"model_id": model_id},
        status="retrying" if state.status == "retrying" else "running",
        event_type=forecast_event,
        payload={
            "model": model_id,
            "forecast_horizon": ctx.horizon,
            "frequency": ctx.frequency,
        },
    )
    if ctx.timestamps is None or ctx.values is None:
        _fail_node(
            state,
            ctx,
            "FORECAST",
            "MissingSeries",
            "Forecast requires timestamps and values",
            [],
        )
        return
    try:
        if ctx.hooks.forecast is not None:
            result = ctx.hooks.forecast(
                timestamps=ctx.timestamps,
                values=ctx.values,
                frequency=ctx.frequency,
                horizon=ctx.horizon,
                model_id=model_id,
                coverage=ctx.coverage,
                seed=ctx.seed,
                seasonal_period=ctx.seasonal_period,
            )
        else:
            result = run_baseline_forecast(
                ctx.timestamps,
                ctx.values,
                frequency=ctx.frequency,
                horizon=ctx.horizon,
                model_id=model_id,
                coverage=ctx.coverage,
                seed=ctx.seed,
                seasonal_period=ctx.seasonal_period,
                generated_at=ctx.generated_at,
            )
    except Exception as exc:
        _fail_node(state, ctx, "FORECAST", type(exc).__name__, str(exc), [])
        return
    state.forecast = result
    if model_id not in state.tried_strategy_ids:
        state.tried_strategy_ids.append(model_id)
    payload = result.model_dump(mode="json")
    eid = _store(state, ctx, "forecast_fit", payload)
    train_range = getattr(result, "training_range", None)
    _record(
        state,
        ctx,
        tool_requested="forecast_fit",
        evidence_ids=[eid],
        decision={"model_id": model_id, "retry_number": state.retry_number},
        status="running" if state.status != "retrying" else "retrying",
        event_type="FORECAST_COMPLETED" if state.status != "retrying" else "RETRY_COMPLETED",
        payload={
            "model": model_id,
            "forecast_horizon": ctx.horizon,
            "frequency": ctx.frequency,
            "training_range": None
            if train_range is None
            else {
                "start": str(getattr(train_range, "start", None)),
                "end": str(getattr(train_range, "end", None)),
            },
            "artifact_ref": eid,
        },
    )
    state.node = "VERIFY"


def _node_verify(state: OrchestratorState, ctx: _Runtime) -> None:
    if state.forecast is None:
        _fail_node(state, ctx, "VERIFY", "MissingForecast", "Verification requires a forecast", [])
        return
    if ctx.hooks.verify is not None:
        ver = ctx.hooks.verify(
            train_values=ctx.values,
            forecast=state.forecast,
            train_timestamps=ctx.timestamps,
        )
    else:
        ver = run_verifier(
            train_values=ctx.values,
            forecast=state.forecast,
            train_timestamps=ctx.timestamps,
            generated_at=ctx.generated_at,
            run_id=state.run_id,
            trajectory_path=ctx.path,
            persist_trajectory=ctx.persist_children,
            case_id=ctx.case_id,
            append_to_trajectory=True,
        )
    eids = _ingest(state, ctx, "verify", ver.evidence)
    state.verification_ran = True
    if ver.report is not None:
        state.verifier_report = ver.report
        state.verification_overall = ver.report.overall_reported
    _record(
        state,
        ctx,
        tool_requested="verify_forecast",
        evidence_ids=eids,
        decision={
            "overall": state.verification_overall,
            "verification_required": True,
        },
        status="running" if state.status != "retrying" else "retrying",
        event_type="VERIFICATION_COMPLETED",
        actor="verifier",
        payload={
            "overall": state.verification_overall,
            "retry_recommended": state.verification_overall == "FAIL",
        },
    )
    if ver.status == "failed" or ver.report is None:
        _fail_node(
            state,
            ctx,
            "VERIFY",
            ver.error_type or "VerifyFailed",
            ver.error_message or "Verifier failed",
            eids,
        )
        return
    state.node = "RETRY_OR_ACCEPT"


def _node_retry_or_accept(state: OrchestratorState, ctx: _Runtime) -> None:
    overall = state.verification_overall
    eids = [key for key in state.evidence][-8:]
    if not state.verification_ran or state.verifier_report is None:
        _fail_node(
            state,
            ctx,
            "RETRY_OR_ACCEPT",
            "VerificationRequired",
            "Cannot accept a result before verification has run",
            [],
        )
        return
    if overall == "FAIL":
        remaining = _next_strategy(state)
        alternative = _next_better_wis_strategy(state)
        can_retry = state.retry_number < state.max_retries and alternative is not None
        if can_retry:
            assert alternative is not None
            current_id = state.selected_strategy_id
            state.retry_number += 1
            state.selected_strategy_id = alternative
            state.status = "retrying"
            eid = _store(
                state,
                ctx,
                "retry_decision",
                {
                    "reason": "verification FAIL and alternative has better official backtest WIS",
                    "current_strategy_id": current_id,
                    "current_official_wis": _official_wis_for(state, current_id),
                    "next_strategy_id": alternative,
                    "next_official_wis": _official_wis_for(state, alternative),
                    "retry_number": state.retry_number,
                },
            )
            _record(
                state,
                ctx,
                tool_requested=None,
                evidence_ids=[eid],
                decision={
                    "action": "retry",
                    "next_strategy_id": alternative,
                    "retry_number": state.retry_number,
                },
                status="retrying",
                event_type="RETRY_REQUESTED",
                payload={
                    "reason": "verification FAIL and alternative has better official backtest WIS",
                    "failed_verification": overall,
                    "alternative_strategy": alternative,
                    "retry_number": state.retry_number,
                },
            )
            state.node = "FORECAST"
            return
        state.review_required = True
        state.accepted = False
        exhausted = state.retry_number >= state.max_retries
        if exhausted:
            reason = (
                "Verification FAIL and retries are exhausted "
                f"(retry_number={state.retry_number}, max={state.max_retries}). "
                "Human review is required."
            )
        elif remaining is not None:
            reason = (
                "Verification FAIL; untried alternative "
                f"{remaining!r} does not have strictly better official backtest WIS "
                f"than {state.selected_strategy_id!r}. Not swapping to a worse model. "
                f"(retry_number={state.retry_number}, max={state.max_retries}). "
                "Human review is required."
            )
        else:
            reason = (
                "Verification FAIL and no alternative strategy remains "
                f"(retry_number={state.retry_number}, max={state.max_retries}). "
                "Human review is required."
            )
        ckpt_id = new_checkpoint_id(state.run_id)
        state.human_checkpoint = HumanCheckpoint(
            required=True,
            status="waiting_for_approval",
            reason=reason,
            evidence_ids=eids,
            triggers=["verification_failed_repeatedly"],
            proposed_transforms=list(state.proposed_transforms),
            source_data_unmodified=True,
            checkpoint_id=ckpt_id,
        )
        state.status = "waiting_for_approval"
        _record(
            state,
            ctx,
            tool_requested=None,
            evidence_ids=eids,
            decision={"action": "review_required", "reason": reason},
            status="waiting_for_approval",
            event_type="HUMAN_CHECKPOINT_CREATED",
            payload={
                "checkpoint_id": ckpt_id,
                "checkpoint_status": "waiting_for_approval",
                "reason": reason,
                "recommendation": "human_review",
            },
        )
        state.node = "ANALYZE"
        return
    state.accepted = overall == "PASS"
    state.review_required = False
    warn = overall == "WARN"
    reason = (
        "Verification WARN: proceed to analyst with uncertainty flagged."
        if warn
        else "Verification PASS: proceed to analyst. Unfalsified is not a guarantee."
    )
    state.human_checkpoint = HumanCheckpoint(
        required=False,
        status="not_required",
        reason=reason,
        evidence_ids=eids,
        proposed_transforms=list(state.proposed_transforms),
        source_data_unmodified=True,
    )
    state.status = "running"
    _record(
        state,
        ctx,
        tool_requested=None,
        evidence_ids=eids,
        decision={"action": "accept", "overall": overall},
        status="running",
        event_type="RETRY_NOT_REQUIRED",
        payload={"overall": overall, "retry_number": state.retry_number},
    )
    state.node = "ANALYZE"


def _node_analyze(state: OrchestratorState, ctx: _Runtime) -> None:
    if ctx.hooks.analyze is not None:
        analyst = ctx.hooks.analyze(
            forecast=state.forecast,
            verifier_report=state.verifier_report,
            strategist_report=state.strategist_report,
            detective_report=state.detective_report,
            context_report=state.context_report,
            diagnostics=state.diagnostics,
        )
    else:
        analyst = run_forecast_analyst(
            forecast=state.forecast,
            verifier_report=state.verifier_report,
            strategist_report=state.strategist_report,
            detective_report=state.detective_report,
            context_report=state.context_report,
            diagnostics=state.diagnostics,
            generated_at=ctx.generated_at,
            run_id=state.run_id,
            trajectory_path=ctx.path,
            persist_trajectory=ctx.persist_children,
            case_id=ctx.case_id,
            append_to_trajectory=True,
        )
    eids = _ingest(state, ctx, "analyze", analyst.evidence)
    if analyst.report is not None:
        state.analyst_report = analyst.report
    step_status: AgentStatus = (
        "waiting_for_approval" if state.status == "waiting_for_approval" else "running"
    )
    _record(
        state,
        ctx,
        tool_requested=None,
        evidence_ids=eids,
        decision={"analyst_status": analyst.status},
        status=step_status,
        event_type="AGENT_COMPLETED",
        actor="forecast_analyst",
        payload={"analyst_status": analyst.status},
    )
    if analyst.status == "failed":
        _fail_node(
            state,
            ctx,
            "ANALYZE",
            analyst.error_type or "AnalyzeFailed",
            analyst.error_message or "Forecast Analyst failed",
            eids,
        )
        return
    state.node = "FINALIZE"


def _node_finalize(state: OrchestratorState, ctx: _Runtime) -> None:
    if state.status != "failed":
        _apply_pending_checkpoint(state)
    if state.status in {"failed", "waiting_for_approval"}:
        final: OrchestratorStatus = state.status
    elif state.review_required:
        final = "waiting_for_approval"
        state.status = "waiting_for_approval"
    else:
        final = "completed"
        state.status = "completed"
    if final == "completed" and not state.verification_ran:
        _halt(state, ctx, "VerificationRequired", "Cannot finalize without verification")
        final = "failed"
    if final == "completed" and state.verification_overall == "FAIL":
        _halt(state, ctx, "UnverifiedFail", "Cannot finalize an accepted FAIL verification")
        final = "failed"
    if final == "completed" and state.human_checkpoint is not None:
        if state.human_checkpoint.status == "approved":
            _halt(state, ctx, "ImplicitApproval", "Graph must not auto-approve a checkpoint")
            final = "failed"
    eid = _store(
        state,
        ctx,
        "finalize",
        {
            "status": final,
            "review_required": state.review_required,
            "verification_overall": state.verification_overall,
            "selected_strategy_id": state.selected_strategy_id,
            "retry_number": state.retry_number,
            "checkpoint_triggers": (
                list(state.human_checkpoint.triggers) if state.human_checkpoint else []
            ),
        },
    )
    if "FINALIZE" not in state.nodes_visited:
        state.nodes_visited.append("FINALIZE")
    state.node = "FINALIZE"
    if (
        state.human_checkpoint is not None
        and state.human_checkpoint.required
        and state.human_checkpoint.status == "waiting_for_approval"
        and not any(
            step.event_type == "HUMAN_CHECKPOINT_CREATED" for step in state.trajectory
        )
    ):
        _record(
            state,
            ctx,
            tool_requested=None,
            evidence_ids=list(state.human_checkpoint.evidence_ids),
            decision={
                "action": "review_required",
                "reason": state.human_checkpoint.reason,
            },
            status="waiting_for_approval",
            event_type="HUMAN_CHECKPOINT_CREATED",
            payload={
                "checkpoint_id": state.human_checkpoint.checkpoint_id,
                "checkpoint_status": "waiting_for_approval",
                "reason": state.human_checkpoint.reason,
                "triggers": list(state.human_checkpoint.triggers),
                "recommendation": "human_review",
            },
        )
    terminal = "RUN_FAILED" if final == "failed" else "RUN_COMPLETED"
    _record(
        state,
        ctx,
        tool_requested=None,
        evidence_ids=[eid],
        decision={"status": final, "review_required": state.review_required},
        status=final,
        event_type=terminal,
        payload={
            "final_status": final,
            "selected_model": state.selected_strategy_id,
            "verification_status": state.verification_overall,
            "retry_count": state.retry_number,
            "review_required": state.review_required,
            "forecast_artifact": "forecast_fit" if state.forecast is not None else None,
            "error_type": state.error_type,
            "error_message": state.error_message,
        },
    )


def _apply_pending_checkpoint(state: OrchestratorState) -> None:
    already_waiting = (
        state.status == "waiting_for_approval"
        or state.review_required
        or (state.human_checkpoint is not None and state.human_checkpoint.required)
    )
    analyst_u = None if state.analyst_report is None else state.analyst_report.overall_uncertainty
    detective_u = (
        None if state.detective_report is None else state.detective_report.overall_uncertainty
    )
    forecastability = (
        None if state.detective_report is None else state.detective_report.forecastability
    )
    triggers = collect_checkpoint_triggers(
        verification_overall=state.verification_overall,
        retry_number=state.retry_number,
        max_retries=state.max_retries,
        proposed_transforms=list(state.proposed_transforms),
        analyst_uncertainty=analyst_u,
        detective_uncertainty=detective_u,
        forecastability=forecastability,
        already_waiting=already_waiting,
    )
    if not triggers:
        return
    eids = [key for key in state.evidence][-8:]
    if state.human_checkpoint is not None:
        eids = list(dict.fromkeys([*state.human_checkpoint.evidence_ids, *eids]))
    reason = reason_for_triggers(triggers)
    if state.human_checkpoint is not None and state.human_checkpoint.reason:
        if state.human_checkpoint.required:
            reason = state.human_checkpoint.reason + " " + reason
    state.review_required = True
    state.accepted = False
    state.status = "waiting_for_approval"
    existing_id = (
        state.human_checkpoint.checkpoint_id if state.human_checkpoint is not None else None
    )
    state.human_checkpoint = HumanCheckpoint(
        required=True,
        status="waiting_for_approval",
        reason=reason.strip(),
        evidence_ids=eids,
        triggers=triggers,
        proposed_transforms=list(state.proposed_transforms),
        source_data_unmodified=True,
        checkpoint_id=existing_id or new_checkpoint_id(state.run_id),
    )


def _backtest_model_ids(ctx: _Runtime) -> tuple[str, ...]:
    """Execute the full allow-list. Strategy shortlist remains a hypothesis only."""
    if ctx.candidate_model_ids:
        return tuple(ctx.candidate_model_ids)
    return BASELINE_MODEL_IDS


def _official_wis_for(state: OrchestratorState, model_id: str | None) -> float | None:
    if model_id is None or state.strategist_report is None:
        return None
    for row in state.strategist_report.comparison:
        if row.model_id == model_id and row.official_wis is not None:
            return float(row.official_wis)
    return None


def _next_strategy(state: OrchestratorState) -> str | None:
    ordered: list[str] = []
    if state.strategist_report is not None:
        ranked = sorted(
            [
                row
                for row in state.strategist_report.comparison
                if row.rank is not None and row.selectable is not False
            ],
            key=lambda row: row.rank,
        )
        ordered.extend(row.model_id for row in ranked)
    for item in state.proposed_candidate_ids:
        if item not in ordered:
            ordered.append(item)
    tried = set(state.tried_strategy_ids)
    for model_id in ordered:
        if model_id not in tried:
            return model_id
    return None


def _next_better_wis_strategy(state: OrchestratorState) -> str | None:
    """Retry only when the next untried model has strictly lower official backtest WIS."""
    current_wis = _official_wis_for(state, state.selected_strategy_id)
    alternative = _next_strategy(state)
    if alternative is None or current_wis is None:
        return None
    alt_wis = _official_wis_for(state, alternative)
    if alt_wis is None or not (alt_wis < current_wis):
        return None
    return alternative


def _first_ranked(report: ForecastStrategistReport | None) -> str | None:
    if report is None:
        return None
    ranked = [row for row in report.comparison if row.rank == 1]
    if ranked:
        return ranked[0].model_id
    if report.proposed_candidate_ids:
        return report.proposed_candidate_ids[0]
    return None


def _diagnostics_from_detective(
    det: DataDetectiveState,
    frequency: str | None,
) -> DatasetDiagnostics:
    payload_by_tool = {item.tool_name: item.payload for item in det.evidence.values()}

    def _flag(name: str) -> bool | None:
        payload = payload_by_tool.get(name)
        if payload is None:
            return None
        detected = payload.get("detected")
        return bool(detected) if isinstance(detected, bool) else None

    n_obs = det.n_observations
    n_missing = None
    quality = payload_by_tool.get("diagnose_quality") or {}
    if isinstance(quality.get("n_missing_values"), int):
        n_missing = quality["n_missing_values"]
    forecastability = None
    if det.report is not None:
        forecastability = det.report.forecastability
    return DatasetDiagnostics(
        n_observations=n_obs,
        frequency=frequency or det.frequency,
        trend_detected=_flag("diagnose_trend"),
        seasonality_detected=_flag("diagnose_seasonality"),
        anomalies_detected=_flag("diagnose_outliers"),
        structural_break_detected=_flag("diagnose_structural_breaks"),
        n_missing_values=n_missing,
        forecastability=forecastability,
        detective_evidence_ids=list(det.evidence.keys()),
    )


def _fail_node(
    state: OrchestratorState,
    ctx: _Runtime,
    node: WorkflowNode,
    error_type: str,
    error_message: str,
    evidence_ids: list[str],
) -> None:
    state.failures.append(
        NodeFailure(
            node=node,
            error_type=error_type,
            error_message=error_message,
            retry_number=state.retry_number,
            evidence_ids=evidence_ids,
        )
    )
    state.error_type = error_type
    state.error_message = error_message
    _halt(state, ctx, error_type, error_message)


def _halt(state: OrchestratorState, ctx: _Runtime, error_type: str, error_message: str) -> None:
    state.status = "failed"
    state.error_type = error_type
    state.error_message = error_message
    state.node = "FINALIZE"


def _ingest(
    state: OrchestratorState,
    ctx: _Runtime,
    prefix: str,
    evidence: dict[str, EvidenceItem],
) -> list[str]:
    eids: list[str] = []
    for item in evidence.values():
        eid = ctx.next_id()
        state.evidence[eid] = EvidenceItem(
            evidence_id=eid,
            tool_name=f"{prefix}:{item.tool_name}",
            payload=dict(item.payload),
        )
        eids.append(eid)
    return eids


def _store(
    state: OrchestratorState,
    ctx: _Runtime,
    tool_name: str,
    payload: JsonObject,
) -> str:
    eid = ctx.next_id()
    state.evidence[eid] = EvidenceItem(evidence_id=eid, tool_name=tool_name, payload=payload)
    return eid


def _record(
    state: OrchestratorState,
    ctx: _Runtime,
    *,
    tool_requested: str | None,
    evidence_ids: list[str],
    status: AgentStatus,
    decision: JsonObject | None = None,
    tool_result: JsonObject | None = None,
    event_type: str | None = None,
    payload: JsonObject | None = None,
    actor: str | None = None,
) -> None:
    snapshot = {
        "node": state.node,
        "retry_number": state.retry_number,
        "selected_strategy_id": state.selected_strategy_id,
        "verification_ran": state.verification_ran,
        "n_failures": len(state.failures),
        "agent_id": ORCHESTRATOR_AGENT_ID,
        "case_id": ctx.case_id,
        "note": "raw series values are not stored in orchestrator state",
    }
    inferred = event_type
    if inferred is None:
        if tool_requested is not None:
            failed = isinstance(tool_result, dict) and tool_result.get("ok") is False
            inferred = "TOOL_FAILED" if failed else "TOOL_COMPLETED"
        elif status == "completed":
            inferred = "RUN_COMPLETED"
        elif status == "failed":
            inferred = "RUN_FAILED"
        elif status == "waiting_for_approval":
            inferred = "HUMAN_CHECKPOINT_CREATED"
        elif status == "retrying":
            inferred = "RETRY_REQUESTED"
        else:
            inferred = "AGENT_DECISION"
    step = TrajectoryStep(
        run_id=state.run_id,
        agent_id=actor or ORCHESTRATOR_AGENT_ID,
        timestamp=utc_now(),
        input_state=snapshot,
        tool_requested=tool_requested,
        tool_result=tool_result,
        decision=decision,
        evidence_ids=evidence_ids,
        retry_number=state.retry_number,
        final_status=status,
        case_id=ctx.case_id,
        event_type=inferred,
        actor=actor or ORCHESTRATOR_AGENT_ID,
        payload=payload,
        safe_tool_arguments=None if tool_requested is None else {"tool_name": tool_requested},
    )
    state.append_step(step)
    persist_trajectory_step(ctx.path, step)


def _evidence_id_factory() -> Callable[[], str]:
    counter = 0

    def _next() -> str:
        nonlocal counter
        counter += 1
        return f"E{counter}"

    return _next
