"""Verifier: challenge a forecast with deterministic checks. Do not emit yhat.

Interpretation may add hypotheses. It must not change a deterministic PASS/WARN/FAIL
without an explicit recorded override reason. No FastAPI. No LLM.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.agents.state import (
    VERIFIER_AGENT_ID,
    VERIFIER_MAX_RETRIES,
    CitedClaim,
    EvidenceItem,
    InvestigationRecommendation,
    TrajectoryStep,
    new_run_id,
)
from app.evidence.logger import persist_trajectory_step, resolve_trajectory_path
from app.forecasting.base import ForecastResult
from app.time_utils import utc_now
from app.tools.verification_tools import (
    VERIFY_FORECAST,
    CheckResult,
    ForecastSnapshot,
    VerificationCheck,
    VerificationToolEnvelope,
    VerifyForecastResult,
    VerifyForecastSpec,
    aggregate_check_results,
    run_named_verification_tool,
)

JsonObject = dict[str, Any]

_REPO_ROOT = Path(__file__).resolve().parents[3]
_TRAJECTORIES_DIR = _REPO_ROOT / "trajectories"


class CheckOverride(BaseModel):
    """Recorded disagreement with a deterministic check. Reason is mandatory."""

    model_config = ConfigDict(extra="forbid")

    check_id: str
    deterministic_result: CheckResult
    interpreted_result: CheckResult
    reason: str = Field(min_length=1)

    @model_validator(mode="after")
    def reason_is_explicit(self) -> CheckOverride:
        if not self.reason.strip():
            msg = "override reason must be a non-empty explanation"
            raise ValueError(msg)
        if self.deterministic_result == self.interpreted_result:
            msg = "override must change the deterministic result"
            raise ValueError(msg)
        return self


class VerifierReport(BaseModel):
    """Verifier output. Deterministic checks are preserved even when interpretation differs."""

    model_config = ConfigDict(extra="forbid")

    overall_deterministic: CheckResult
    overall_reported: CheckResult
    challenged: bool
    deterministic_checks: list[VerificationCheck]
    reported_checks: list[VerificationCheck]
    overrides: list[CheckOverride] = Field(default_factory=list)
    claims: list[CitedClaim]
    risks: list[CitedClaim]
    investigations: list[InvestigationRecommendation]
    evidence_ids_used: list[str]
    modified_dataset: bool = False
    emitted_forecast: bool = False
    forecast_adjusted: bool = False

    @model_validator(mode="after")
    def no_silent_override_or_forecast(self) -> VerifierReport:
        if self.modified_dataset:
            msg = "Verifier must not modify the dataset"
            raise ValueError(msg)
        if self.emitted_forecast or self.forecast_adjusted:
            msg = "Verifier must not emit or adjust a numerical forecast"
            raise ValueError(msg)
        det = {item.check_id: item.result for item in self.deterministic_checks}
        rep = {item.check_id: item.result for item in self.reported_checks}
        override_by_id = {item.check_id: item for item in self.overrides}
        for check_id, det_result in det.items():
            reported = rep.get(check_id)
            if reported is None:
                msg = f"reported checks missing deterministic check {check_id}"
                raise ValueError(msg)
            if reported != det_result:
                override = override_by_id.get(check_id)
                if override is None:
                    msg = (
                        f"check {check_id} changed from {det_result} to {reported} "
                        "without a recorded override reason"
                    )
                    raise ValueError(msg)
                if override.deterministic_result != det_result:
                    msg = f"override for {check_id} must cite the original deterministic result"
                    raise ValueError(msg)
                if override.interpreted_result != reported:
                    msg = f"override for {check_id} must match the reported result"
                    raise ValueError(msg)
        expected_reported = aggregate_check_results(self.reported_checks)
        if self.overall_reported != expected_reported:
            msg = "overall_reported must match reported check aggregation"
            raise ValueError(msg)
        expected_det = aggregate_check_results(self.deterministic_checks)
        if self.overall_deterministic != expected_det:
            msg = "overall_deterministic must match deterministic check aggregation"
            raise ValueError(msg)
        for claim in (*self.claims, *self.risks):
            if not claim.evidence_ids:
                msg = "every material conclusion must reference evidence IDs"
                raise ValueError(msg)
        return self


class VerifierState(BaseModel):
    """Explicit verifier state. Series values are not stored here."""

    model_config = ConfigDict(extra="forbid")

    run_id: str
    agent_id: str = VERIFIER_AGENT_ID
    status: str
    overall_result: CheckResult | None = None
    evidence: dict[str, EvidenceItem] = Field(default_factory=dict)
    tool_errors: list[str] = Field(default_factory=list)
    report: VerifierReport | None = None
    retry_number: int = 0
    trajectory: list[TrajectoryStep] = Field(default_factory=list)
    error_type: str | None = None
    error_message: str | None = None
    case_id: str | None = None

    def append_step(self, step: TrajectoryStep) -> None:
        self.trajectory.append(step)


def run_verifier(
    *,
    train_values: pd.Series | np.ndarray | list[float] | None,
    forecast: ForecastSnapshot | ForecastResult | None,
    train_timestamps: pd.Series | pd.DatetimeIndex | None = None,
    actuals: pd.Series | np.ndarray | list[float] | None = None,
    residuals: pd.Series | np.ndarray | list[float] | None = None,
    spec: VerifyForecastSpec | None = None,
    overrides: Sequence[CheckOverride] | None = None,
    run_id: str | None = None,
    generated_at: datetime | None = None,
    trajectory_path: Path | None = None,
    persist_trajectory: bool = True,
    case_id: str | None = None,
    append_to_trajectory: bool = False,
) -> VerifierState:
    """Run deterministic verification, then interpret without silent override.

    Does not fit models and does not change yhat. Overrides must include a reason.
    """
    created = generated_at if generated_at is not None else utc_now()
    rid = run_id if run_id is not None else new_run_id(created, prefix="verifier")
    state = VerifierState(run_id=rid, status="running", retry_number=0, case_id=case_id)
    out_path = resolve_trajectory_path(
        persist=persist_trajectory,
        path=trajectory_path,
        run_id=rid,
        default_dir=_TRAJECTORIES_DIR,
        truncate=not append_to_trajectory,
    )

    snapshot = _input_snapshot(train_values, forecast, actuals, residuals)
    next_id = _evidence_id_factory()
    options = spec if spec is not None else VerifyForecastSpec()
    _record_step(
        state,
        created=created,
        snapshot=snapshot,
        tool_requested=None,
        tool_result=None,
        evidence_ids=[],
        path=out_path,
        status="running",
        event_type="VERIFICATION_STARTED",
        payload={"model": snapshot.get("model"), "n_forecast": snapshot.get("n_forecast")},
    )

    envelope, retries = _call_tool(
        train_values=train_values,
        forecast=forecast,
        train_timestamps=train_timestamps,
        actuals=actuals,
        residuals=residuals,
        spec=options,
    )
    verify_eid = _store_evidence(state, envelope, next_id)
    _record_step(
        state,
        created=created,
        snapshot=snapshot,
        tool_requested=VERIFY_FORECAST,
        tool_result=_envelope_dump(envelope),
        evidence_ids=[verify_eid],
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
            error_type=envelope.error_type or "InvalidVerificationInput",
            error_message=envelope.error_message or "verify_forecast failed",
            extra_eids=[verify_eid],
        )

    det_result = VerifyForecastResult.model_validate(envelope.payload)
    report = _synthesize_report(
        det_result=det_result,
        verify_eid=verify_eid,
        overrides=list(overrides) if overrides is not None else [],
    )
    state.report = report
    state.overall_result = report.overall_reported
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
        event_type="VERIFICATION_COMPLETED",
        payload={
            "overall": report.overall_reported,
            "checks": [
                {"check_id": item.check_id, "result": item.result}
                for item in report.reported_checks
            ],
            "retry_recommended": report.overall_reported == "FAIL",
        },
    )
    return state


def _call_tool(
    *,
    train_values: pd.Series | np.ndarray | list[float] | None,
    forecast: ForecastSnapshot | ForecastResult | None,
    train_timestamps: pd.Series | pd.DatetimeIndex | None,
    actuals: pd.Series | np.ndarray | list[float] | None,
    residuals: pd.Series | np.ndarray | list[float] | None,
    spec: VerifyForecastSpec,
) -> tuple[VerificationToolEnvelope, int]:
    retries = 0
    envelope = run_named_verification_tool(
        VERIFY_FORECAST,
        train_values=train_values,
        forecast=forecast,
        train_timestamps=train_timestamps,
        actuals=actuals,
        residuals=residuals,
        spec=spec,
    )
    while not envelope.ok and retries < VERIFIER_MAX_RETRIES:
        retries += 1
        envelope = run_named_verification_tool(
            VERIFY_FORECAST,
            train_values=train_values,
            forecast=forecast,
            train_timestamps=train_timestamps,
            actuals=actuals,
            residuals=residuals,
            spec=spec,
        )
    return envelope, retries


def _synthesize_report(
    *,
    det_result: VerifyForecastResult,
    verify_eid: str,
    overrides: list[CheckOverride],
) -> VerifierReport:
    reported = [item.model_copy(deep=True) for item in det_result.checks]
    override_by_id = {item.check_id: item for item in overrides}
    for item in reported:
        override = override_by_id.get(item.check_id)
        if override is None:
            continue
        item.result = override.interpreted_result
        item.explanation = (
            item.explanation + " Interpretation override recorded: " + override.reason.strip()
        )
        item.evidence = {
            **item.evidence,
            "override_reason": override.reason.strip(),
            "deterministic_result": override.deterministic_result,
        }
    overall_reported = aggregate_check_results(reported)
    claims: list[CitedClaim] = [
        CitedClaim(
            kind="observation",
            topic="verification",
            statement=det_result.summary,
            evidence_ids=[verify_eid],
            uncertainty="low",
            why_uncertainty=(
                "Check results are copied from verify_forecast; they are not recomputed."
            ),
        )
    ]
    risks: list[CitedClaim] = []
    investigations: list[InvestigationRecommendation] = []
    for check in reported:
        if check.result == "FAIL":
            claims.append(
                CitedClaim(
                    kind="observation",
                    topic="verification",
                    statement=f"{check.check_id} FAIL: {check.explanation}",
                    evidence_ids=[verify_eid],
                    uncertainty="low",
                    why_uncertainty="FAIL is a deterministic challenge, not an LLM score.",
                )
            )
        elif check.result == "WARN":
            risks.append(
                CitedClaim(
                    kind="observation",
                    topic="verification",
                    statement=f"{check.check_id} WARN: {check.explanation}",
                    evidence_ids=[verify_eid],
                    uncertainty="medium",
                    why_uncertainty="WARN means the check could not confirm the property.",
                )
            )
    if overrides:
        claims.append(
            CitedClaim(
                kind="hypothesis",
                topic="verification",
                statement=(
                    "Interpretation overrides were recorded with reasons. Deterministic "
                    "results remain in deterministic_checks."
                ),
                evidence_ids=[verify_eid],
                uncertainty="high",
                why_uncertainty="Overrides are interpretation, not new numerical evidence.",
            )
        )
    if overall_reported == "FAIL":
        investigations.append(
            InvestigationRecommendation(
                action="Do not accept this forecast without human review of the FAIL checks.",
                evidence_ids=[verify_eid],
                priority="high",
            )
        )
    elif overall_reported == "WARN":
        investigations.append(
            InvestigationRecommendation(
                action="Review WARN checks before treating the forecast as verified.",
                evidence_ids=[verify_eid],
                priority="medium",
            )
        )
    else:
        claims.append(
            CitedClaim(
                kind="hypothesis",
                topic="verification",
                statement=(
                    "Deterministic checks did not falsify the artifact. That is not a claim "
                    "that the forecast is true."
                ),
                evidence_ids=[verify_eid],
                uncertainty="medium",
                why_uncertainty="Unfalsified is not the same as validated against unseen outcomes.",
            )
        )
    return VerifierReport(
        overall_deterministic=det_result.overall_result,
        overall_reported=overall_reported,
        challenged=overall_reported != "PASS",
        deterministic_checks=list(det_result.checks),
        reported_checks=reported,
        overrides=overrides,
        claims=claims,
        risks=risks,
        investigations=investigations,
        evidence_ids_used=[verify_eid],
        modified_dataset=False,
        emitted_forecast=False,
        forecast_adjusted=False,
    )


def _fail(
    state: VerifierState,
    *,
    created: datetime,
    snapshot: JsonObject,
    path: Path | None,
    next_id: Callable[[], str],
    error_type: str,
    error_message: str,
    extra_eids: list[str],
) -> VerifierState:
    state.status = "failed"
    state.error_type = error_type
    state.error_message = error_message
    state.tool_errors.append(error_message)
    fail_eid = _store_payload(
        state,
        next_id,
        tool_name="verifier_failure",
        payload={"error_type": error_type, "error_message": error_message},
    )
    eids = list(extra_eids) + [fail_eid]
    placeholder = VerificationCheck(
        check_id="V00_input",
        name="verification input",
        result="FAIL",
        severity="high",
        explanation=error_message,
        evidence={"error_type": error_type},
    )
    claim = CitedClaim(
        kind="observation",
        topic="verification",
        statement=f"Verification did not complete: {error_message}",
        evidence_ids=eids,
        uncertainty="high",
        why_uncertainty="The verify_forecast tool did not return checks.",
    )
    report = VerifierReport(
        overall_deterministic="FAIL",
        overall_reported="FAIL",
        challenged=True,
        deterministic_checks=[placeholder],
        reported_checks=[placeholder],
        overrides=[],
        claims=[claim],
        risks=[],
        investigations=[
            InvestigationRecommendation(
                action="Supply a valid training series and forecast artifact, then re-run.",
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
    state.overall_result = "FAIL"
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
    state: VerifierState,
    envelope: VerificationToolEnvelope,
    next_id: Callable[[], str],
) -> str:
    return _store_payload(state, next_id, envelope.tool_name, dict(envelope.payload))


def _store_payload(
    state: VerifierState,
    next_id: Callable[[], str],
    tool_name: str,
    payload: JsonObject,
) -> str:
    eid = next_id()
    state.evidence[eid] = EvidenceItem(evidence_id=eid, tool_name=tool_name, payload=payload)
    return eid


def _envelope_dump(envelope: VerificationToolEnvelope) -> JsonObject:
    return {
        "ok": envelope.ok,
        "error_type": envelope.error_type,
        "error_message": envelope.error_message,
        "payload": envelope.payload,
    }


def _record_step(
    state: VerifierState,
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
            inferred = "VERIFICATION_COMPLETED"
        else:
            inferred = "AGENT_DECISION"
    step = TrajectoryStep(
        run_id=state.run_id,
        agent_id=VERIFIER_AGENT_ID,
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
        actor=VERIFIER_AGENT_ID,
        payload=payload,
        safe_tool_arguments=None if tool_requested is None else {"tool_name": tool_requested},
    )
    state.retry_number = max(state.retry_number, retry_number)
    state.append_step(step)
    persist_trajectory_step(path, step)


def _input_snapshot(
    train_values: pd.Series | np.ndarray | list[float] | None,
    forecast: ForecastSnapshot | ForecastResult | None,
    actuals: pd.Series | np.ndarray | list[float] | None,
    residuals: pd.Series | np.ndarray | list[float] | None,
) -> JsonObject:
    n_train = None if train_values is None else int(np.asarray(train_values).size)
    n_fc = None
    model = None
    if isinstance(forecast, ForecastResult):
        n_fc = len(forecast.yhat)
        model = forecast.model
    elif isinstance(forecast, ForecastSnapshot):
        n_fc = len(forecast.yhat)
        model = forecast.model
    return {
        "n_train": n_train,
        "n_forecast": n_fc,
        "n_actuals": None if actuals is None else int(np.asarray(actuals).size),
        "n_residuals": None if residuals is None else int(np.asarray(residuals).size),
        "model": model,
        "agent_id": VERIFIER_AGENT_ID,
        "note": "raw series values are not stored in agent state",
    }


def _evidence_id_factory() -> Callable[[], str]:
    counter = 0

    def _next() -> str:
        nonlocal counter
        counter += 1
        return f"E{counter}"

    return _next
