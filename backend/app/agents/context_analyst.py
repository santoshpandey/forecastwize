"""Context Analyst: record optional event/context labels as facts, not causes.

Does not emit yhat. Does not adjust forecasts. Does not invent events or assert
causality. No FastAPI. No LLM.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

import pandas as pd
from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.agents.state import (
    CONTEXT_ANALYST_AGENT_ID,
    CONTEXT_ANALYST_MAX_RETRIES,
    CitedClaim,
    EvidenceItem,
    InvestigationRecommendation,
    TrajectoryStep,
    UncertaintyLevel,
    new_run_id,
)
from app.evidence.logger import persist_trajectory_step, resolve_trajectory_path
from app.time_utils import utc_now
from app.tools.context_tools import (
    INSPECT_CONTEXT,
    ContextToolEnvelope,
    ContextualRecord,
    EventKind,
    InspectContextResult,
    InspectContextSpec,
    LabeledWindow,
    run_named_context_tool,
)

JsonObject = dict[str, Any]
FindingKind = Literal["observed_fact", "possible_explanation"]

_REPO_ROOT = Path(__file__).resolve().parents[3]
_TRAJECTORIES_DIR = _REPO_ROOT / "trajectories"

_CAUSAL_MARKERS = (
    " caused ",
    " causes ",
    " causing ",
    " because of ",
    " led to ",
    " resulted in ",
    " was caused ",
)


class ContextDiagnosticsHint(BaseModel):
    """Optional caller diagnostics. Coincidence is not identification."""

    model_config = ConfigDict(extra="forbid")

    anomalies_detected: bool | None = None
    structural_break_detected: bool | None = None
    anomaly_timestamps: list[datetime] = Field(default_factory=list)
    break_timestamp: datetime | None = None


class ContextFinding(BaseModel):
    """One fact or a labeled hypothesis. Causal claims are forbidden without evidence."""

    model_config = ConfigDict(extra="forbid")

    kind: FindingKind
    statement: str
    evidence_ids: list[str] = Field(min_length=1)
    event_kind: EventKind | None = None
    uncertainty: UncertaintyLevel
    why_uncertainty: str
    asserts_causality: bool = False

    @model_validator(mode="after")
    def forbid_causal_assertion(self) -> ContextFinding:
        if self.asserts_causality:
            msg = "Context Analyst must not assert causality; no identification evidence exists"
            raise ValueError(msg)
        lowered = f" {self.statement.lower()} "
        if any(marker in lowered for marker in _CAUSAL_MARKERS):
            msg = "statement must not assert a causal relationship"
            raise ValueError(msg)
        if self.kind == "possible_explanation":
            if "possible explanation" not in self.statement.lower():
                msg = "possible explanations must be labeled as such"
                raise ValueError(msg)
        return self


class ContextAnalystReport(BaseModel):
    """Structured context report. Forecasts are not produced or adjusted."""

    model_config = ConfigDict(extra="forbid")

    context_available: bool
    unavailable_reason: str | None
    observed_facts: list[ContextFinding]
    possible_explanations: list[ContextFinding]
    recognized_event_kinds: list[EventKind]
    claims: list[CitedClaim]
    risks: list[CitedClaim]
    investigations: list[InvestigationRecommendation]
    evidence_ids_used: list[str]
    modified_dataset: bool = False
    emitted_forecast: bool = False
    forecast_adjusted: bool = False

    @model_validator(mode="after")
    def facts_are_not_causes_and_forecasts_are_untouched(self) -> ContextAnalystReport:
        if self.modified_dataset:
            msg = "Context Analyst must not modify the dataset"
            raise ValueError(msg)
        if self.emitted_forecast or self.forecast_adjusted:
            msg = "Context Analyst must not emit or adjust a numerical forecast"
            raise ValueError(msg)
        for fact in self.observed_facts:
            if fact.kind != "observed_fact":
                msg = "observed_facts must use kind observed_fact"
                raise ValueError(msg)
        for item in self.possible_explanations:
            if item.kind != "possible_explanation":
                msg = "possible_explanations must use kind possible_explanation"
                raise ValueError(msg)
        if not self.context_available:
            if not self.unavailable_reason:
                msg = "unavailable context analysis must state a reason"
                raise ValueError(msg)
            if "unavailable" not in self.unavailable_reason.lower():
                msg = "unavailable reason must state that contextual analysis is unavailable"
                raise ValueError(msg)
        for claim in (*self.claims, *self.risks):
            if not claim.evidence_ids:
                msg = "every material conclusion must reference evidence IDs"
                raise ValueError(msg)
        return self


class ContextAnalystState(BaseModel):
    """Explicit Context Analyst state. Series values and forecasts are not stored."""

    model_config = ConfigDict(extra="forbid")

    run_id: str
    agent_id: str = CONTEXT_ANALYST_AGENT_ID
    status: str
    context_available: bool | None = None
    evidence: dict[str, EvidenceItem] = Field(default_factory=dict)
    tool_errors: list[str] = Field(default_factory=list)
    report: ContextAnalystReport | None = None
    retry_number: int = 0
    trajectory: list[TrajectoryStep] = Field(default_factory=list)
    error_type: str | None = None
    error_message: str | None = None
    case_id: str | None = None

    def append_step(self, step: TrajectoryStep) -> None:
        self.trajectory.append(step)


def run_context_analyst(
    *,
    timestamps: pd.Series | pd.DatetimeIndex | Sequence[datetime] | None = None,
    event_labels: Sequence[object] | pd.Series | None = None,
    context_labels: Sequence[object] | pd.Series | None = None,
    records: Sequence[ContextualRecord] | None = None,
    notes: str | None = None,
    diagnostics_hint: ContextDiagnosticsHint | None = None,
    run_id: str | None = None,
    generated_at: datetime | None = None,
    trajectory_path: Path | None = None,
    persist_trajectory: bool = True,
    case_id: str | None = None,
    append_to_trajectory: bool = False,
) -> ContextAnalystState:
    """Inspect optional context/event labels and report facts vs hypotheses.

    Does not read series values, does not fit models, and does not change forecasts.
    """
    created = generated_at if generated_at is not None else utc_now()
    rid = run_id if run_id is not None else new_run_id(created, prefix="context-analyst")
    state = ContextAnalystState(run_id=rid, status="running", retry_number=0, case_id=case_id)
    out_path = resolve_trajectory_path(
        persist=persist_trajectory,
        path=trajectory_path,
        run_id=rid,
        default_dir=_TRAJECTORIES_DIR,
        truncate=not append_to_trajectory,
    )

    snapshot = _input_snapshot(
        n_timestamps=_optional_len(timestamps),
        n_event=_optional_len(event_labels),
        n_context=_optional_len(context_labels),
        n_records=len(records) if records is not None else 0,
        notes_provided=bool(notes),
    )
    next_id = _evidence_id_factory()
    _record_step(
        state,
        created=created,
        snapshot=snapshot,
        tool_requested=None,
        tool_result=None,
        evidence_ids=[],
        path=out_path,
        status="running",
        event_type="AGENT_STARTED",
        payload={"agent": CONTEXT_ANALYST_AGENT_ID},
    )
    spec = InspectContextSpec(
        notes_provided=bool(notes),
        notes_character_count=len(notes) if notes is not None else None,
    )

    envelope, retries = _call_tool(
        timestamps=timestamps,
        event_labels=event_labels,
        context_labels=context_labels,
        records=records,
        spec=spec,
    )
    inspect_eid = _store_evidence(state, envelope, next_id)
    _record_step(
        state,
        created=created,
        snapshot=snapshot,
        tool_requested=INSPECT_CONTEXT,
        tool_result=_envelope_dump(envelope),
        evidence_ids=[inspect_eid],
        path=out_path,
        status="running",
        retry_number=retries,
    )
    if not envelope.ok:
        return _fail(
            state,
            created=created,
            snapshot=snapshot,
            path=out_path,
            next_id=next_id,
            error_type=envelope.error_type or "InvalidContextInput",
            error_message=envelope.error_message or "inspect_context failed",
            extra_eids=[inspect_eid],
        )

    result = InspectContextResult.model_validate(envelope.payload)
    hint_eid: str | None = None
    if diagnostics_hint is not None:
        hint_eid = _store_payload(
            state,
            next_id,
            tool_name="diagnostics_hint",
            payload=diagnostics_hint.model_dump(mode="json"),
        )
        _record_step(
            state,
            created=created,
            snapshot=snapshot,
            tool_requested=None,
            tool_result=None,
            evidence_ids=[hint_eid],
            path=out_path,
            status="running",
            decision={"note": "Caller diagnostics are hints, not causal evidence."},
        )

    report = _synthesize_report(
        result=result,
        inspect_eid=inspect_eid,
        hint_eid=hint_eid,
        hint=diagnostics_hint,
        notes_provided=bool(notes),
    )
    state.report = report
    state.context_available = report.context_available
    state.status = "completed"
    _record_step(
        state,
        created=created,
        snapshot=snapshot,
        tool_requested=None,
        tool_result=None,
        evidence_ids=report.evidence_ids_used,
        path=out_path,
        status="completed",
        decision=report.model_dump(mode="json"),
    )
    return state


def _call_tool(
    *,
    timestamps: pd.Series | pd.DatetimeIndex | Sequence[datetime] | None,
    event_labels: Sequence[object] | pd.Series | None,
    context_labels: Sequence[object] | pd.Series | None,
    records: Sequence[ContextualRecord] | None,
    spec: InspectContextSpec,
) -> tuple[ContextToolEnvelope, int]:
    retries = 0
    envelope = run_named_context_tool(
        INSPECT_CONTEXT,
        timestamps=timestamps,
        event_labels=event_labels,
        context_labels=context_labels,
        records=records,
        spec=spec,
    )
    while not envelope.ok and retries < CONTEXT_ANALYST_MAX_RETRIES:
        retries += 1
        envelope = run_named_context_tool(
            INSPECT_CONTEXT,
            timestamps=timestamps,
            event_labels=event_labels,
            context_labels=context_labels,
            records=records,
            spec=spec,
        )
    return envelope, retries


def _synthesize_report(
    *,
    result: InspectContextResult,
    inspect_eid: str,
    hint_eid: str | None,
    hint: ContextDiagnosticsHint | None,
    notes_provided: bool,
) -> ContextAnalystReport:
    facts: list[ContextFinding] = []
    explanations: list[ContextFinding] = []
    claims: list[CitedClaim] = []
    risks: list[CitedClaim] = []
    investigations: list[InvestigationRecommendation] = []
    used = [inspect_eid]
    if hint_eid is not None:
        used.append(hint_eid)

    if not result.context_available:
        reason = result.unavailable_reason or (
            "No context or event data was provided. Contextual analysis is unavailable."
        )
        fact = ContextFinding(
            kind="observed_fact",
            statement=reason,
            evidence_ids=[inspect_eid],
            uncertainty="low",
            why_uncertainty="Absence of labels is directly observed from the input.",
        )
        facts.append(fact)
        claims.append(_claim_from_finding(fact, topic="context"))
        if notes_provided:
            note_fact = ContextFinding(
                kind="observed_fact",
                statement=(
                    "Caller notes were provided but are not structured event labels. "
                    "Notes are not treated as observed events. Contextual analysis is unavailable."
                ),
                evidence_ids=[inspect_eid],
                uncertainty="medium",
                why_uncertainty="Free text is not parsed into event types.",
            )
            facts.append(note_fact)
            claims.append(_claim_from_finding(note_fact, topic="context"))
        investigations.append(
            InvestigationRecommendation(
                action=(
                    "Supply optional context/event labels if business events were recorded; "
                    "do not infer them."
                ),
                evidence_ids=[inspect_eid],
                priority="low",
            )
        )
        return ContextAnalystReport(
            context_available=False,
            unavailable_reason=reason,
            observed_facts=facts,
            possible_explanations=[],
            recognized_event_kinds=[],
            claims=claims,
            risks=risks,
            investigations=investigations,
            evidence_ids_used=used,
            modified_dataset=False,
            emitted_forecast=False,
            forecast_adjusted=False,
        )

    facts.append(
        ContextFinding(
            kind="observed_fact",
            statement=result.summary,
            evidence_ids=[inspect_eid],
            uncertainty="low",
            why_uncertainty="Window counts come from the inspect_context tool, not from inference.",
        )
    )
    for window in result.windows:
        facts.append(_fact_for_window(window, inspect_eid))
    claims.extend(_claim_from_finding(item, topic="context") for item in facts)

    explanations.extend(
        _explanations_for_windows(
            windows=result.windows,
            inspect_eid=inspect_eid,
            hint_eid=hint_eid,
            hint=hint,
        )
    )
    claims.extend(_claim_from_finding(item, topic="context") for item in explanations)
    risks.append(
        CitedClaim(
            kind="hypothesis",
            topic="context",
            statement=(
                "Labeled events remain possible explanations only. They were not used to "
                "change a forecast and are not identified as causes."
            ),
            evidence_ids=used,
            uncertainty="high",
            why_uncertainty="No causal identification procedure was executed.",
        )
    )
    if result.unrecognized_labels:
        investigations.append(
            InvestigationRecommendation(
                action=(
                    "Review unrecognized labels with a human before treating them "
                    "as known event types."
                ),
                evidence_ids=[inspect_eid],
                priority="medium",
            )
        )
    investigations.append(
        InvestigationRecommendation(
            action=(
                "If a causal story is required, use an identification design outside this agent. "
                "Do not adjust forecasts from labels alone."
            ),
            evidence_ids=used,
            priority="high",
        )
    )
    return ContextAnalystReport(
        context_available=True,
        unavailable_reason=None,
        observed_facts=facts,
        possible_explanations=explanations,
        recognized_event_kinds=list(result.recognized_kinds),
        claims=claims,
        risks=risks,
        investigations=investigations,
        evidence_ids_used=used,
        modified_dataset=False,
        emitted_forecast=False,
        forecast_adjusted=False,
    )


def _fact_for_window(window: LabeledWindow, inspect_eid: str) -> ContextFinding:
    span = _window_span(window)
    kind_text = (
        f"classified as {window.event_kind}"
        if window.event_kind != "unrecognized"
        else "not classified as a known event type"
    )
    statement = (
        f"Observed fact: {window.source} label {window.raw_label!r} on {window.n_steps} "
        f"step(s){span} was provided ({kind_text}). This is not a causal finding."
    )
    return ContextFinding(
        kind="observed_fact",
        statement=statement,
        evidence_ids=[inspect_eid],
        event_kind=window.event_kind,
        uncertainty="low",
        why_uncertainty="The label was present in the caller input; it was not inferred.",
    )


def _explanations_for_windows(
    *,
    windows: list[LabeledWindow],
    inspect_eid: str,
    hint_eid: str | None,
    hint: ContextDiagnosticsHint | None,
) -> list[ContextFinding]:
    eids = [inspect_eid]
    if hint_eid is not None:
        eids.append(hint_eid)
    kinds = []
    for window in windows:
        if window.event_kind != "unrecognized" and window.event_kind not in kinds:
            kinds.append(window.event_kind)
    kind_list = ", ".join(kinds) if kinds else "labeled windows"
    overlap = _hint_overlap(windows, hint)
    if overlap:
        statement = (
            f"Possible explanation: caller-flagged {overlap} coincides with {kind_list}. "
            "Coincidence of labels and diagnostics is not a causal finding."
        )
        uncertainty: UncertaintyLevel = "high"
        why = "Overlap is timestamp alignment only; no identification test was run."
    elif hint is not None and (
        hint.anomalies_detected is True or hint.structural_break_detected is True
    ):
        statement = (
            "Possible explanation: caller diagnostics flag unusual series behavior, and "
            f"{kind_list} are present. The labels are one possible account, not an "
            "identified cause."
        )
        uncertainty = "high"
        why = "Diagnostics were supplied by the caller and were not re-tested here."
    else:
        statement = (
            f"Possible explanation: if independently observed series changes occur during "
            f"{kind_list}, the provided labels are one possible account. No causal test was run "
            "and no forecast was adjusted."
        )
        uncertainty = "high"
        why = "No series values were inspected; this remains an untested hypothesis."
    return [
        ContextFinding(
            kind="possible_explanation",
            statement=statement,
            evidence_ids=eids,
            uncertainty=uncertainty,
            why_uncertainty=why,
        )
    ]


def _hint_overlap(windows: list[LabeledWindow], hint: ContextDiagnosticsHint | None) -> str | None:
    if hint is None:
        return None
    hits: list[str] = []
    for stamp in hint.anomaly_timestamps:
        if _stamp_in_windows(stamp, windows):
            hits.append("anomalies")
            break
    if hint.break_timestamp is not None and _stamp_in_windows(hint.break_timestamp, windows):
        hits.append("a structural-break timestamp")
    if not hits:
        return None
    return " and ".join(hits)


def _stamp_in_windows(stamp: datetime, windows: list[LabeledWindow]) -> bool:
    for window in windows:
        if window.start is None or window.end is None:
            continue
        if window.start <= stamp <= window.end:
            return True
    return False


def _window_span(window: LabeledWindow) -> str:
    if window.start is None and window.end is None:
        if window.start_index is None:
            return ""
        return f" (indices {window.start_index}-{window.end_index})"
    start = window.start.isoformat().replace("+00:00", "Z") if window.start is not None else "?"
    end = window.end.isoformat().replace("+00:00", "Z") if window.end is not None else "?"
    return f" ({start} to {end})"


def _claim_from_finding(finding: ContextFinding, *, topic: str) -> CitedClaim:
    kind = "observation" if finding.kind == "observed_fact" else "hypothesis"
    return CitedClaim(
        kind=kind,  # type: ignore[arg-type]
        topic=topic,  # type: ignore[arg-type]
        statement=finding.statement,
        evidence_ids=finding.evidence_ids,
        uncertainty=finding.uncertainty,
        why_uncertainty=finding.why_uncertainty,
    )


def _fail(
    state: ContextAnalystState,
    *,
    created: datetime,
    snapshot: JsonObject,
    path: Path | None,
    next_id: Callable[[], str],
    error_type: str,
    extra_eids: list[str],
    error_message: str,
) -> ContextAnalystState:
    state.status = "failed"
    state.error_type = error_type
    state.error_message = error_message
    state.tool_errors.append(error_message)
    state.context_available = False
    fail_eid = _store_payload(
        state,
        next_id,
        tool_name="context_analyst_failure",
        payload={"error_type": error_type, "error_message": error_message},
    )
    eids = list(extra_eids) + [fail_eid]
    reason = f"Contextual analysis is unavailable because inspection failed: {error_message}"
    fact = ContextFinding(
        kind="observed_fact",
        statement=reason,
        evidence_ids=eids,
        uncertainty="high",
        why_uncertainty="The inspect_context tool did not return a valid label inventory.",
    )
    report = ContextAnalystReport(
        context_available=False,
        unavailable_reason=reason,
        observed_facts=[fact],
        possible_explanations=[],
        recognized_event_kinds=[],
        claims=[_claim_from_finding(fact, topic="context")],
        risks=[],
        investigations=[
            InvestigationRecommendation(
                action="Fix the recorded context input error, then re-run. Do not invent labels.",
                evidence_ids=eids,
                priority="high",
            )
        ],
        evidence_ids_used=eids,
        modified_dataset=False,
        emitted_forecast=False,
        forecast_adjusted=False,
    )
    state.report = report
    _record_step(
        state,
        created=created,
        snapshot=snapshot,
        tool_requested=None,
        tool_result=None,
        evidence_ids=eids,
        path=path,
        status="failed",
        decision=report.model_dump(mode="json"),
    )
    return state


def _store_evidence(
    state: ContextAnalystState,
    envelope: ContextToolEnvelope,
    next_id: Callable[[], str],
) -> str:
    return _store_payload(state, next_id, envelope.tool_name, dict(envelope.payload))


def _store_payload(
    state: ContextAnalystState,
    next_id: Callable[[], str],
    tool_name: str,
    payload: JsonObject,
) -> str:
    eid = next_id()
    state.evidence[eid] = EvidenceItem(evidence_id=eid, tool_name=tool_name, payload=payload)
    return eid


def _envelope_dump(envelope: ContextToolEnvelope) -> JsonObject:
    return {
        "ok": envelope.ok,
        "error_type": envelope.error_type,
        "error_message": envelope.error_message,
        "payload": envelope.payload,
    }


def _record_step(
    state: ContextAnalystState,
    *,
    created: datetime,
    snapshot: JsonObject,
    tool_requested: str | None,
    tool_result: JsonObject | None,
    evidence_ids: list[str],
    path: Path | None,
    status: str,
    decision: JsonObject | None = None,
    retry_number: int = 0,
    event_type: str | None = None,
    payload: JsonObject | None = None,
) -> None:
    inferred = event_type
    if inferred is None:
        if tool_requested is not None:
            failed = isinstance(tool_result, dict) and tool_result.get("ok") is False
            inferred = "TOOL_FAILED" if failed else "TOOL_COMPLETED"
        elif status == "completed":
            inferred = "AGENT_COMPLETED"
        else:
            inferred = "AGENT_DECISION"
    step = TrajectoryStep(
        run_id=state.run_id,
        agent_id=CONTEXT_ANALYST_AGENT_ID,
        timestamp=created,
        input_state=snapshot,
        tool_requested=tool_requested,
        tool_result=tool_result,
        decision=decision,
        evidence_ids=evidence_ids,
        retry_number=retry_number,
        final_status=status,  # type: ignore[arg-type]
        case_id=state.case_id,
        event_type=inferred,
        actor=CONTEXT_ANALYST_AGENT_ID,
        payload=payload,
        safe_tool_arguments=None if tool_requested is None else {"tool_name": tool_requested},
    )
    state.retry_number = max(state.retry_number, retry_number)
    state.append_step(step)
    persist_trajectory_step(path, step)


def _input_snapshot(
    *,
    n_timestamps: int | None,
    n_event: int | None,
    n_context: int | None,
    n_records: int,
    notes_provided: bool,
) -> JsonObject:
    return {
        "n_timestamps": n_timestamps,
        "n_event_labels": n_event,
        "n_context_labels": n_context,
        "n_records": n_records,
        "notes_provided": notes_provided,
        "agent_id": CONTEXT_ANALYST_AGENT_ID,
        "note": "raw labels are not stored in agent state; series values are not read",
    }


def _optional_len(values: object | None) -> int | None:
    if values is None:
        return None
    return len(values)  # type: ignore[arg-type]


def _evidence_id_factory() -> Callable[[], str]:
    counter = 0

    def _next() -> str:
        nonlocal counter
        counter += 1
        return f"E{counter}"

    return _next
