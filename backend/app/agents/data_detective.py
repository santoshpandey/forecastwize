"""Data Detective: interpret deterministic diagnostics. Never emit yhat or modify data."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from app.agents.state import (
    DATA_DETECTIVE_AGENT_ID,
    DATA_DETECTIVE_MAX_RETRIES,
    CitedClaim,
    DataDetectiveReport,
    DataDetectiveState,
    EvidenceItem,
    InvestigationRecommendation,
    ProposedTransform,
    TrajectoryStep,
    UncertaintyLevel,
    new_run_id,
)
from app.data.validator import SeriesInspection
from app.evidence.logger import persist_trajectory_step
from app.forecasting.base import ForecastInterfaceError
from app.time_utils import utc_now
from app.tools.data_tools import (
    DIAGNOSE_QUALITY,
    INSPECT_SERIES,
    DataToolEnvelope,
    DataToolSpec,
    inspect_series,
    reject_unknown_data_tool,
    run_named_data_tool,
)

JsonObject = dict[str, Any]

_REPO_ROOT = Path(__file__).resolve().parents[3]
_TRAJECTORIES_DIR = _REPO_ROOT / "trajectories"

_SCREEN_TOOLS = (
    "diagnose_outliers",
    "diagnose_rolling_anomalies",
    "diagnose_trend",
    "diagnose_seasonality",
    "diagnose_structural_breaks",
)

_TOPIC_BY_TOOL = {
    "diagnose_outliers": "anomalies",
    "diagnose_rolling_anomalies": "anomalies",
    "diagnose_trend": "trend",
    "diagnose_seasonality": "seasonality",
    "diagnose_structural_breaks": "structural_change",
    "diagnose_quality": "data_quality",
    "inspect_series": "input",
}


def run_data_detective(
    timestamps: pd.Series | pd.DatetimeIndex | None,
    values: pd.Series | np.ndarray | None,
    *,
    frequency: str | None = None,
    seasonal_period: int | None = None,
    run_id: str | None = None,
    generated_at: datetime | None = None,
    trajectory_path: Path | None = None,
    persist_trajectory: bool = True,
) -> DataDetectiveState:
    """Run the Data Detective pipeline: approved diagnostic tools, then structured claims.

    Does not fit forecast models, does not invent statistics, and does not modify
    `timestamps` or `values`. Material claims cite evidence IDs from tool results.
    """
    created = generated_at if generated_at is not None else utc_now()
    rid = run_id if run_id is not None else new_run_id(created)
    spec = DataToolSpec(frequency=frequency, seasonal_period=seasonal_period)
    n_obs = None if values is None else int(np.asarray(values).size)
    state = DataDetectiveState(
        run_id=rid,
        status="running",
        frequency=frequency,
        n_observations=n_obs,
        retry_number=0,
    )
    out_path = trajectory_path
    if persist_trajectory and out_path is None:
        out_path = _TRAJECTORIES_DIR / f"{rid}.jsonl"
    if out_path is not None:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text("", encoding="utf-8", newline="\n")

    snapshot = _input_snapshot(n_obs, frequency, seasonal_period)
    next_id = _evidence_id_factory()

    inspection: SeriesInspection | None = None
    inspect_ok = False
    try:
        inspect_env, inspect_retries = _call_tool(
            INSPECT_SERIES,
            timestamps,
            values,
            spec,
            inspection=None,
        )
        inspect_eid = _store_evidence(state, inspect_env, next_id)
        _record_tool_step(
            state,
            created=created,
            snapshot=snapshot,
            envelope=inspect_env,
            evidence_ids=[inspect_eid],
            retry_number=inspect_retries,
            path=out_path,
        )
        inspect_ok = inspect_env.ok
        if inspect_ok:
            inspection = inspect_series(timestamps, values)
            inferred = inspect_env.payload.get("frequency")
            if state.frequency is None and isinstance(inferred, str):
                state.frequency = inferred
                spec = spec.model_copy(update={"frequency": inferred})
    except ForecastInterfaceError as exc:
        inspect_env = DataToolEnvelope(
            tool_name=INSPECT_SERIES,
            ok=False,
            payload={"is_valid": False, "summary": str(exc), "error_codes": ["invalid_input"]},
            error_type="InvalidInput",
            error_message=str(exc),
        )
        inspect_eid = _store_evidence(state, inspect_env, next_id)
        state.tool_errors.append(str(exc))
        _record_tool_step(
            state,
            created=created,
            snapshot=snapshot,
            envelope=inspect_env,
            evidence_ids=[inspect_eid],
            retry_number=0,
            path=out_path,
        )

    quality_env, quality_retries = _call_tool(
        DIAGNOSE_QUALITY,
        timestamps,
        values,
        spec,
        inspection=inspection,
    )
    quality_eid = _store_evidence(state, quality_env, next_id)
    _record_tool_step(
        state,
        created=created,
        snapshot=snapshot,
        envelope=quality_env,
        evidence_ids=[quality_eid],
        retry_number=quality_retries,
        path=out_path,
    )

    skip_screens = not inspect_ok
    if skip_screens:
        state.status = "failed"
        state.error_type = inspect_env.error_type or "InvalidInput"
        state.error_message = inspect_env.error_message or inspect_env.payload.get("summary")
        report = _report_invalid(state)
        state.report = report
        _record_decision_step(state, created=created, snapshot=snapshot, path=out_path)
        return state

    for tool_name in _SCREEN_TOOLS:
        env, retries = _call_tool(
            tool_name,
            timestamps,
            values,
            spec,
            inspection=inspection,
        )
        eid = _store_evidence(state, env, next_id)
        if not env.ok:
            state.tool_errors.append(env.error_message or tool_name)
        _record_tool_step(
            state,
            created=created,
            snapshot=snapshot,
            envelope=env,
            evidence_ids=[eid],
            retry_number=retries,
            path=out_path,
        )

    state.report = _synthesize_report(state)
    state.status = "completed"
    _record_decision_step(state, created=created, snapshot=snapshot, path=out_path)
    return state


def _call_tool(
    name: str,
    timestamps: object,
    values: object,
    spec: DataToolSpec,
    *,
    inspection: SeriesInspection | None,
) -> tuple[DataToolEnvelope, int]:
    reject_unknown_data_tool(name)
    last_error: Exception | None = None
    for attempt in range(DATA_DETECTIVE_MAX_RETRIES + 1):
        try:
            return (
                run_named_data_tool(
                    name,
                    timestamps,  # type: ignore[arg-type]
                    values,  # type: ignore[arg-type]
                    spec,
                    inspection=inspection,
                ),
                attempt,
            )
        except ForecastInterfaceError as exc:
            payload = {
                "summary": str(exc),
                "detected": False,
                "error_codes": ["invalid_input"],
            }
            return (
                DataToolEnvelope(
                    tool_name=name,
                    ok=False,
                    payload=payload,
                    error_type="InvalidInput",
                    error_message=str(exc),
                ),
                attempt,
            )
        except Exception as exc:
            last_error = exc
            if attempt >= DATA_DETECTIVE_MAX_RETRIES:
                break
    assert last_error is not None
    return (
        DataToolEnvelope(
            tool_name=name,
            ok=False,
            payload={"summary": str(last_error), "detected": False},
            error_type=type(last_error).__name__,
            error_message=str(last_error),
        ),
        DATA_DETECTIVE_MAX_RETRIES,
    )


def _store_evidence(
    state: DataDetectiveState,
    envelope: DataToolEnvelope,
    next_id: Callable[[], str],
) -> str:
    eid = next_id()
    state.evidence[eid] = EvidenceItem(
        evidence_id=eid,
        tool_name=envelope.tool_name,
        payload=dict(envelope.payload),
    )
    return eid


def _record_tool_step(
    state: DataDetectiveState,
    *,
    created: datetime,
    snapshot: JsonObject,
    envelope: DataToolEnvelope,
    evidence_ids: list[str],
    retry_number: int,
    path: Path | None,
) -> None:
    status = "retrying" if retry_number else "running"
    if not envelope.ok and envelope.tool_name == INSPECT_SERIES:
        status = "failed"
    step = TrajectoryStep(
        run_id=state.run_id,
        agent_id=DATA_DETECTIVE_AGENT_ID,
        timestamp=created,
        input_state=snapshot,
        tool_requested=envelope.tool_name,
        tool_result={
            "ok": envelope.ok,
            "error_type": envelope.error_type,
            "error_message": envelope.error_message,
            "payload": envelope.payload,
        },
        decision=None,
        evidence_ids=evidence_ids,
        retry_number=retry_number,
        final_status=status,
    )
    state.retry_number = max(state.retry_number, retry_number)
    state.append_step(step)
    _persist_step(path, step)


def _record_decision_step(
    state: DataDetectiveState,
    *,
    created: datetime,
    snapshot: JsonObject,
    path: Path | None,
) -> None:
    report = state.report
    used = list(report.evidence_ids_used) if report is not None else []
    step = TrajectoryStep(
        run_id=state.run_id,
        agent_id=DATA_DETECTIVE_AGENT_ID,
        timestamp=created,
        input_state=snapshot,
        tool_requested=None,
        tool_result=None,
        decision=report.model_dump(mode="json") if report is not None else None,
        evidence_ids=used,
        retry_number=state.retry_number,
        final_status=state.status,
    )
    state.append_step(step)
    _persist_step(path, step)


def _persist_step(path: Path | None, step: TrajectoryStep) -> None:
    persist_trajectory_step(path, step)


def _input_snapshot(
    n_obs: int | None,
    frequency: str | None,
    seasonal_period: int | None,
) -> JsonObject:
    return {
        "n_observations": n_obs,
        "frequency": frequency,
        "seasonal_period": seasonal_period,
        "agent_id": DATA_DETECTIVE_AGENT_ID,
        "note": "raw series values are not stored in agent state",
    }


def _evidence_id_factory():
    counter = 0

    def _next() -> str:
        nonlocal counter
        counter += 1
        return f"E{counter}"

    return _next


def _report_invalid(state: DataDetectiveState) -> DataDetectiveReport:
    inspect_eid = _eid_for_tool(state, INSPECT_SERIES)
    quality_eid = _eid_for_tool(state, DIAGNOSE_QUALITY)
    eids = [eid for eid in (inspect_eid, quality_eid) if eid is not None]
    if not eids:
        msg = "invalid input produced no inspect evidence"
        raise ForecastInterfaceError(msg)
    message = state.error_message or "Input is invalid."
    claim = CitedClaim(
        kind="observation",
        topic="input",
        statement=f"The series could not be profiled: {message}",
        evidence_ids=eids,
        uncertainty="high",
        why_uncertainty="Inspection did not produce a valid derived series.",
    )
    risk = CitedClaim(
        kind="observation",
        topic="data_quality",
        statement="Forecasting is blocked until the input is valid.",
        evidence_ids=eids,
        uncertainty="high",
        why_uncertainty="No reliable diagnostics exist for an invalid series.",
    )
    investigation = InvestigationRecommendation(
        action=(
            "Fix timestamps/values (length, parseability, required columns) and re-run inspection."
        ),
        evidence_ids=eids,
        priority="high",
    )
    return DataDetectiveReport(
        forecastability="unknown",
        forecastability_rationale="Input failed inspection; forecastability is unknown.",
        forecastability_evidence_ids=eids,
        overall_uncertainty="high",
        claims=[claim],
        risks=[risk],
        investigations=[investigation],
        evidence_ids_used=eids,
        modified_dataset=False,
        emitted_forecast=False,
    )


def _synthesize_report(state: DataDetectiveState) -> DataDetectiveReport:
    claims: list[CitedClaim] = []
    risks: list[CitedClaim] = []
    investigations: list[InvestigationRecommendation] = []
    proposed_transforms: list[ProposedTransform] = []
    used: list[str] = []

    inspect_eid = _eid_for_tool(state, INSPECT_SERIES)
    quality_eid = _eid_for_tool(state, DIAGNOSE_QUALITY)
    inspect_payload = state.evidence[inspect_eid].payload if inspect_eid else {}
    quality_payload = state.evidence[quality_eid].payload if quality_eid else {}

    if inspect_eid:
        used.append(inspect_eid)
        claims.append(
            CitedClaim(
                kind="observation",
                topic="input",
                statement=_copy_summary(inspect_payload, fallback="Inspection completed."),
                evidence_ids=[inspect_eid],
                uncertainty=_uncertainty_from_confidence(
                    inspect_payload.get("frequency_confidence")
                ),
                why_uncertainty="Profile statistics come only from the inspect_series tool.",
            )
        )
        if inspect_payload.get("has_event"):
            n_ev = inspect_payload.get("n_event_non_null", 0)
            claims.append(
                CitedClaim(
                    kind="observation",
                    topic="input",
                    statement=(
                        f"An event column is present with {n_ev} non-null label(s). "
                        "Those labels are recorded as provided; no event was invented."
                    ),
                    evidence_ids=[inspect_eid],
                    uncertainty="low",
                    why_uncertainty="Column presence is taken from inspection only.",
                )
            )
        elif inspect_payload.get("has_event") is False:
            claims.append(
                CitedClaim(
                    kind="observation",
                    topic="input",
                    statement=("No event column was provided. No business events are inferred."),
                    evidence_ids=[inspect_eid],
                    uncertainty="low",
                    why_uncertainty="Absence of a column is not evidence that events occurred.",
                )
            )

    if quality_eid:
        used.append(quality_eid)
        quality_detected = bool(quality_payload.get("detected"))
        claims.append(
            CitedClaim(
                kind="observation",
                topic="data_quality",
                statement=_copy_summary(quality_payload, fallback="Quality screen completed."),
                evidence_ids=[quality_eid],
                uncertainty="medium" if quality_detected else "low",
                why_uncertainty=(
                    "Quality flags are descriptive counts from the profile, not repairs."
                ),
            )
        )
        if quality_payload.get("n_missing_values"):
            risks.append(
                CitedClaim(
                    kind="observation",
                    topic="data_quality",
                    statement=(
                        "Missing values are present. Baseline models do not impute; "
                        "an explicit missing-value policy is required."
                    ),
                    evidence_ids=[quality_eid],
                    uncertainty="medium",
                    why_uncertainty="Missingness is counted; the mechanism is unknown.",
                )
            )
            investigations.append(
                InvestigationRecommendation(
                    action=(
                        "Choose an explicit missing-value policy (or fail). "
                        "Do not silently fill or drop points."
                    ),
                    evidence_ids=[quality_eid],
                    priority="high",
                )
            )
            proposed_transforms.append(
                ProposedTransform(
                    name="missing_value_policy",
                    policy="fail_or_explicit_named_policy",
                    reason=(
                        "Missing values are present. A named policy is required; "
                        "source data is not filled or dropped."
                    ),
                    applied=False,
                )
            )
        if (
            quality_payload.get("zero_share") is not None
            and float(quality_payload["zero_share"]) >= 0.3
        ):
            risks.append(
                CitedClaim(
                    kind="hypothesis",
                    topic="data_quality",
                    statement=(
                        "A high share of zeros may indicate intermittent demand; "
                        "standard continuous-error models may be a poor match."
                    ),
                    evidence_ids=[quality_eid],
                    uncertainty="high",
                    why_uncertainty="Zero share is observed; demand process is not identified.",
                )
            )
            investigations.append(
                InvestigationRecommendation(
                    action=(
                        "Investigate intermittency (zero process vs demand size) "
                        "before model choice."
                    ),
                    evidence_ids=[quality_eid],
                    priority="medium",
                )
            )
        if not quality_payload.get("frequency_resolved"):
            investigations.append(
                InvestigationRecommendation(
                    action="Supply an explicit frequency alias; do not assume one.",
                    evidence_ids=[quality_eid],
                    priority="high",
                )
            )

    inconclusive_screens: list[str] = []
    flagged: list[str] = []
    for tool_name, topic in _TOPIC_BY_TOOL.items():
        if tool_name in {INSPECT_SERIES, DIAGNOSE_QUALITY}:
            continue
        eid = _eid_for_tool(state, tool_name)
        if eid is None:
            continue
        used.append(eid)
        payload = state.evidence[eid].payload
        detected = bool(payload.get("detected"))
        summary = _copy_summary(payload, fallback=f"{tool_name} completed.")
        insufficient = _is_insufficient(payload)
        confidence = str(payload.get("confidence") or "low")
        uncertainty = _uncertainty_from_confidence(confidence)
        if insufficient:
            inconclusive_screens.append(tool_name)
            claims.append(
                CitedClaim(
                    kind="observation",
                    topic=topic,  # type: ignore[arg-type]
                    statement=(
                        f"{tool_name} did not make a positive detection because the screen "
                        f"had insufficient evidence: {summary}"
                    ),
                    evidence_ids=[eid],
                    uncertainty="high",
                    why_uncertainty=(
                        "Insufficient history or unresolved period; absence of a flag "
                        "is not a negative finding."
                    ),
                )
            )
        elif detected:
            flagged.append(tool_name)
            claims.append(
                CitedClaim(
                    kind="observation",
                    topic=topic,  # type: ignore[arg-type]
                    statement=summary,
                    evidence_ids=[eid],
                    uncertainty=uncertainty,
                    why_uncertainty="; ".join(_limitations(payload)[:2])
                    or "Screening rule, not a formal hypothesis test.",
                )
            )
            if tool_name in {"diagnose_outliers", "diagnose_rolling_anomalies"}:
                risks.append(
                    CitedClaim(
                        kind="observation",
                        topic="anomalies",
                        statement=(
                            "Anomaly flags exist. They are not clipped or removed; "
                            "investigate the cited indices/timestamps."
                        ),
                        evidence_ids=[eid],
                        uncertainty=uncertainty,
                        why_uncertainty=(
                            "Modified z-score is a heuristic; seasonality can inflate flags."
                        ),
                    )
                )
                investigations.append(
                    InvestigationRecommendation(
                        action=(
                            "Review flagged points against operations context. Do not auto-clip."
                        ),
                        evidence_ids=[eid],
                        priority="high",
                    )
                )
            if tool_name == "diagnose_structural_breaks":
                risks.append(
                    CitedClaim(
                        kind="observation",
                        topic="structural_change",
                        statement=(
                            "A mean-shift screen flagged a candidate split. "
                            "This is not a Chow test and does not prove a lasting regime change."
                        ),
                        evidence_ids=[eid],
                        uncertainty=uncertainty,
                        why_uncertainty=(
                            "Single-split mean scan; variance/seasonal resets are not modeled."
                        ),
                    )
                )
                risks.append(
                    CitedClaim(
                        kind="hypothesis",
                        topic="structural_change",
                        statement=(
                            "If the level shift persists into the future, a single global "
                            "model may be poorly calibrated. That is an interpretation, "
                            "not a forecast."
                        ),
                        evidence_ids=[eid],
                        uncertainty="high",
                        why_uncertainty=(
                            "The screen does not predict whether the new level continues."
                        ),
                    )
                )
                investigations.append(
                    InvestigationRecommendation(
                        action=(
                            "Investigate the split time; consider a human checkpoint "
                            "before using one model across regimes."
                        ),
                        evidence_ids=[eid],
                        priority="high",
                    )
                )
            if tool_name == "diagnose_trend":
                claims.append(
                    CitedClaim(
                        kind="hypothesis",
                        topic="trend",
                        statement=(
                            "The flagged monotonic association with time may or may not continue; "
                            "the screen is not a projection."
                        ),
                        evidence_ids=[eid],
                        uncertainty="high",
                        why_uncertainty="Spearman vs index is not a forecast and has no p-value.",
                    )
                )
            if tool_name == "diagnose_seasonality":
                claims.append(
                    CitedClaim(
                        kind="hypothesis",
                        topic="seasonality",
                        statement=(
                            "Repeating variation at the screened period may remain relevant, "
                            "but calendar effects were not modeled."
                        ),
                        evidence_ids=[eid],
                        uncertainty="high",
                        why_uncertainty="ACF at one lag is not a seasonal model.",
                    )
                )
        else:
            claims.append(
                CitedClaim(
                    kind="observation",
                    topic=topic,  # type: ignore[arg-type]
                    statement=(
                        f"{tool_name} did not flag a detection at its configured "
                        f"threshold: {summary}"
                    ),
                    evidence_ids=[eid],
                    uncertainty=uncertainty,
                    why_uncertainty="A negative screen is not proof that the phenomenon is absent.",
                )
            )

    if inconclusive_screens:
        eids = [
            eid for name in inconclusive_screens if (eid := _eid_for_tool(state, name)) is not None
        ]
        investigations.append(
            InvestigationRecommendation(
                action=(
                    "Collect a longer history (or supply an explicit seasonal period) before "
                    "treating inconclusive screens as negative evidence."
                ),
                evidence_ids=eids or ([inspect_eid] if inspect_eid else used[:1]),
                priority="high" if len(inconclusive_screens) >= 2 else "medium",
            )
        )

    forecastability, rationale, f_eids, overall_u = _forecastability(
        state,
        inspect_payload,
        quality_payload,
        flagged,
        inconclusive_screens,
        inspect_eid,
        quality_eid,
    )
    used.extend(f_eids)
    claims.append(
        CitedClaim(
            kind="observation",
            topic="forecastability",
            statement=rationale,
            evidence_ids=f_eids,
            uncertainty=overall_u,
            why_uncertainty=(
                "Forecastability is qualitative and does not include a numerical forecast."
            ),
        )
    )
    if not investigations:
        fallback = quality_eid or inspect_eid
        if fallback:
            investigations.append(
                InvestigationRecommendation(
                    action=(
                        "No blocking quality error was recorded. Treat screens as heuristics "
                        "and keep transforms explicit if any are proposed later."
                    ),
                    evidence_ids=[fallback],
                    priority="low",
                )
            )

    unique_used = list(dict.fromkeys(used + f_eids))
    return DataDetectiveReport(
        forecastability=forecastability,
        forecastability_rationale=rationale,
        forecastability_evidence_ids=f_eids,
        overall_uncertainty=overall_u,
        claims=claims,
        risks=risks,
        investigations=investigations,
        evidence_ids_used=unique_used,
        proposed_transforms=proposed_transforms,
        modified_dataset=False,
        emitted_forecast=False,
    )


def _forecastability(
    state: DataDetectiveState,
    inspect_payload: JsonObject,
    quality_payload: JsonObject,
    flagged: list[str],
    inconclusive: list[str],
    inspect_eid: str | None,
    quality_eid: str | None,
) -> tuple[str, str, list[str], UncertaintyLevel]:
    n = state.n_observations or 0
    n_missing = int(
        quality_payload.get("n_missing_values") or inspect_payload.get("n_missing_values") or 0
    )
    eids = [eid for eid in (inspect_eid, quality_eid) if eid is not None]
    break_eid = _eid_for_tool(state, "diagnose_structural_breaks")
    outlier_eid = _eid_for_tool(state, "diagnose_outliers")
    if n < 8:
        return (
            "poor",
            f"History length {n} is below the minimum used even for outlier screening.",
            eids,
            "high",
        )
    if inconclusive or n < 20:
        extra = [eid for eid in (break_eid,) if eid]
        return (
            "limited",
            "History is short relative to conservative diagnostic minima; "
            "several screens are inconclusive.",
            eids + extra,
            "high",
        )
    if n_missing:
        return (
            "limited",
            "Missing values are present and are not imputed; forecastability is "
            "limited until a policy is chosen.",
            eids,
            "high",
        )
    if "diagnose_structural_breaks" in flagged and break_eid:
        return (
            "limited",
            "A structural-break screen flagged a mean shift; a single-regime "
            "forecast may be unreliable.",
            eids + [break_eid],
            "high",
        )
    if "diagnose_outliers" in flagged and outlier_eid:
        return (
            "limited",
            "Anomaly flags are present; point accuracy may be sensitive to those observations.",
            eids + [outlier_eid],
            "medium",
        )
    return (
        "adequate",
        "Inspection succeeded, quality did not record blocking errors, and "
        "history is long enough for the conservative screens.",
        eids,
        "medium",
    )


def _eid_for_tool(state: DataDetectiveState, tool_name: str) -> str | None:
    for eid, item in state.evidence.items():
        if item.tool_name == tool_name:
            return eid
    return None


def _copy_summary(payload: JsonObject, *, fallback: str) -> str:
    evidence = payload.get("evidence")
    if isinstance(evidence, dict) and evidence.get("summary"):
        return str(evidence["summary"])
    if payload.get("summary"):
        return str(payload["summary"])
    return fallback


def _limitations(payload: JsonObject) -> list[str]:
    raw = payload.get("limitations")
    if isinstance(raw, list):
        return [str(item) for item in raw]
    return []


def _is_insufficient(payload: JsonObject) -> bool:
    summary = _copy_summary(payload, fallback="").lower()
    blobs = summary + " " + " ".join(_limitations(payload)).lower()
    tokens = ("insufficient", "need at least", "too small", "unresolved", "window too small")
    return any(token in blobs for token in tokens)


def _uncertainty_from_confidence(value: object) -> UncertaintyLevel:
    if value == "high":
        return "low"
    if value == "medium":
        return "medium"
    return "high"
