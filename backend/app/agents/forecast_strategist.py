"""Forecast Strategist: propose candidates, evaluate via backtest, recommend with evidence.

Does not emit yhat. Does not claim a model is superior until evaluate_candidates
has returned official backtest WIS. No FastAPI. No LLM.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.agents.state import (
    FORECAST_STRATEGIST_AGENT_ID,
    FORECAST_STRATEGIST_MAX_RETRIES,
    CitedClaim,
    EvidenceItem,
    InvestigationRecommendation,
    SelectionRule,
    TrajectoryStep,
    new_run_id,
)
from app.data.seasonality import period_from_frequency
from app.evidence.logger import persist_trajectory_step
from app.forecasting.base import ForecastInterfaceError
from app.time_utils import utc_now
from app.tools.forecasting_tools import (
    EVALUATE_CANDIDATES,
    LIST_SUPPORTED_MODELS,
    CandidateEvalRow,
    EvaluateCandidatesSpec,
    ForecastToolEnvelope,
    reject_unknown_forecast_tool,
    reject_unsupported_model_ids,
    run_named_forecast_tool,
)

JsonObject = dict[str, Any]

_REPO_ROOT = Path(__file__).resolve().parents[3]
_TRAJECTORIES_DIR = _REPO_ROOT / "trajectories"


class DatasetDiagnostics(BaseModel):
    """Structured diagnostics the Strategist may inspect. None means not provided."""

    model_config = ConfigDict(extra="forbid")

    n_observations: int | None = None
    frequency: str | None = None
    seasonal_period: int | None = None
    trend_detected: bool | None = None
    seasonality_detected: bool | None = None
    anomalies_detected: bool | None = None
    structural_break_detected: bool | None = None
    n_missing_values: int | None = None
    forecastability: str | None = None
    detective_evidence_ids: list[str] = Field(default_factory=list)
    summary: str | None = None


class BusinessContext(BaseModel):
    """Optional caller-supplied context. The agent must not invent events."""

    model_config = ConfigDict(extra="forbid")

    notes: str | None = None
    has_event_column: bool | None = None
    n_event_non_null: int | None = None


class ForecastStrategistReport(BaseModel):
    """Strategy recommendation. No yhat. Superiority requires executed backtest evidence."""

    model_config = ConfigDict(extra="forbid")

    proposed_candidate_ids: list[str]
    recommended_strategy_id: str | None
    selection_rule: SelectionRule
    backtest_executed: bool
    comparison: list[CandidateEvalRow]
    claims: list[CitedClaim]
    risks: list[CitedClaim]
    investigations: list[InvestigationRecommendation]
    evidence_ids_used: list[str]
    modified_dataset: bool = False
    emitted_forecast: bool = False

    @model_validator(mode="after")
    def superiority_requires_backtest_evidence(self) -> ForecastStrategistReport:
        if self.modified_dataset:
            msg = "Forecast Strategist must not modify the dataset"
            raise ValueError(msg)
        if self.emitted_forecast:
            msg = "Forecast Strategist must not emit a numerical forecast"
            raise ValueError(msg)
        if self.recommended_strategy_id is not None:
            if not self.backtest_executed:
                msg = "cannot recommend a strategy before backtesting has been executed"
                raise ValueError(msg)
            if self.selection_rule != "official_backtest_wis":
                msg = "strategy recommendation must use official backtest WIS"
                raise ValueError(msg)
            if not self.comparison:
                msg = "strategy recommendation requires comparison evidence"
                raise ValueError(msg)
        for claim in (*self.claims, *self.risks):
            if not claim.evidence_ids:
                msg = "every material conclusion must reference evidence IDs"
                raise ValueError(msg)
        return self


class ForecastStrategistState(BaseModel):
    """Explicit Forecast Strategist state. Series values are not stored here."""

    model_config = ConfigDict(extra="forbid")

    run_id: str
    agent_id: str = FORECAST_STRATEGIST_AGENT_ID
    status: str
    frequency: str | None = None
    horizon: int | None = None
    n_observations: int | None = None
    evidence: dict[str, EvidenceItem] = Field(default_factory=dict)
    tool_errors: list[str] = Field(default_factory=list)
    report: ForecastStrategistReport | None = None
    retry_number: int = 0
    trajectory: list[TrajectoryStep] = Field(default_factory=list)
    error_type: str | None = None
    error_message: str | None = None

    def append_step(self, step: TrajectoryStep) -> None:
        self.trajectory.append(step)


def diagnostics_are_missing(diagnostics: DatasetDiagnostics | None) -> bool:
    if diagnostics is None:
        return True
    return (
        diagnostics.n_observations is None
        and diagnostics.trend_detected is None
        and diagnostics.seasonality_detected is None
        and diagnostics.anomalies_detected is None
        and diagnostics.structural_break_detected is None
    )


def propose_candidate_ids(diagnostics: DatasetDiagnostics) -> list[str]:
    """Hypothesis-only shortlist. Not a claim that any model is superior."""
    out: list[str] = ["naive"]
    if diagnostics.seasonality_detected is True:
        out.extend(["seasonal_naive", "ets"])
    if diagnostics.trend_detected is True:
        if "ets" not in out:
            out.append("ets")
        out.append("arima")
    return list(dict.fromkeys(out))


def backtest_min_train_size(n: int, horizon: int, period: int | None) -> int | None:
    max_allowed = n - horizon
    if max_allowed < 1:
        return None
    needed = 8
    if period is not None:
        needed = max(needed, int(period))
    return min(needed, max_allowed)


def backtest_is_feasible(n: int, horizon: int, min_train_size: int) -> bool:
    last = n - 1 - horizon
    first = min_train_size - 1
    return n >= 1 and horizon >= 1 and min_train_size >= 1 and first <= last


def run_forecast_strategist(
    timestamps: pd.Series | pd.DatetimeIndex | None,
    values: pd.Series | np.ndarray | None,
    *,
    horizon: int,
    frequency: str,
    diagnostics: DatasetDiagnostics | None,
    context: BusinessContext | None = None,
    candidate_model_ids: tuple[str, ...] | None = None,
    seasonal_period: int | None = None,
    seed: int | None = None,
    run_id: str | None = None,
    generated_at: datetime | None = None,
    trajectory_path: Path | None = None,
    persist_trajectory: bool = True,
) -> ForecastStrategistState:
    """Inspect diagnostics, propose candidates, backtest, recommend with evidence."""
    created = generated_at if generated_at is not None else utc_now()
    rid = run_id if run_id is not None else new_run_id(created, prefix="forecast-strategist")
    n_obs = None if values is None else int(np.asarray(values, dtype=float).size)
    state = ForecastStrategistState(
        run_id=rid,
        status="running",
        frequency=frequency,
        horizon=horizon,
        n_observations=n_obs,
    )
    out_path = trajectory_path
    if persist_trajectory and out_path is None:
        out_path = _TRAJECTORIES_DIR / f"{rid}.jsonl"
    if out_path is not None:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text("", encoding="utf-8", newline="\n")

    snapshot = _input_snapshot(n_obs, frequency, horizon, seasonal_period)
    next_id = _evidence_id_factory()

    if not frequency or not str(frequency).strip():
        return _fail(
            state,
            created=created,
            snapshot=snapshot,
            path=out_path,
            next_id=next_id,
            error_type="InvalidInput",
            error_message="frequency is required",
        )
    if horizon < 1:
        return _fail(
            state,
            created=created,
            snapshot=snapshot,
            path=out_path,
            next_id=next_id,
            error_type="InvalidInput",
            error_message="horizon must be >= 1",
        )

    if diagnostics_are_missing(diagnostics):
        return _fail(
            state,
            created=created,
            snapshot=snapshot,
            path=out_path,
            next_id=next_id,
            error_type="MissingDiagnostics",
            error_message="dataset diagnostics are required and were not provided",
        )
    assert diagnostics is not None

    diag_eid = _store_payload(
        state,
        next_id,
        tool_name="diagnostics_input",
        payload=diagnostics.model_dump(mode="json"),
    )
    _record_step(
        state,
        created=created,
        snapshot=snapshot,
        tool_requested=None,
        tool_result={"ok": True, "payload": state.evidence[diag_eid].payload},
        evidence_ids=[diag_eid],
        path=out_path,
        status="running",
        decision={"step": "inspect_diagnostics"},
    )

    period = seasonal_period
    if period is None:
        period = diagnostics.seasonal_period
    if period is None:
        period = period_from_frequency(frequency)

    if candidate_model_ids is not None:
        try:
            reject_unsupported_model_ids(candidate_model_ids)
        except ForecastInterfaceError as exc:
            return _fail(
                state,
                created=created,
                snapshot=snapshot,
                path=out_path,
                next_id=next_id,
                error_type="UnsupportedModel",
                error_message=str(exc),
                extra_eids=[diag_eid],
            )
        proposed = list(dict.fromkeys(candidate_model_ids))
    else:
        proposed = propose_candidate_ids(diagnostics)

    propose_eid = _store_payload(
        state,
        next_id,
        tool_name="candidate_proposal",
        payload={
            "model_ids": proposed,
            "summary": (
                "Candidate shortlist is a hypothesis from diagnostics, not a superiority ranking."
            ),
        },
    )
    _record_step(
        state,
        created=created,
        snapshot=snapshot,
        tool_requested=None,
        tool_result=None,
        evidence_ids=[diag_eid, propose_eid],
        path=out_path,
        status="running",
        decision={"step": "identify_candidates", "model_ids": proposed},
    )

    n = diagnostics.n_observations if diagnostics.n_observations is not None else n_obs
    if n is None or values is None or timestamps is None:
        return _fail(
            state,
            created=created,
            snapshot=snapshot,
            path=out_path,
            next_id=next_id,
            error_type="InsufficientData",
            error_message="observation count or series is missing; cannot backtest",
            extra_eids=[diag_eid, propose_eid],
        )
    min_train = backtest_min_train_size(int(n), horizon, period)
    if min_train is None or not backtest_is_feasible(int(n), horizon, min_train):
        return _fail(
            state,
            created=created,
            snapshot=snapshot,
            path=out_path,
            next_id=next_id,
            error_type="InsufficientData",
            error_message=(
                f"insufficient data for backtest: n={n}, horizon={horizon}, "
                f"min_train_size={min_train}"
            ),
            extra_eids=[diag_eid, propose_eid],
        )

    supported_env, supported_retries = _call_tool(
        LIST_SUPPORTED_MODELS,
        timestamps=None,
        values=None,
        spec=None,
    )
    supported_eid = _store_evidence(state, supported_env, next_id)
    _record_step(
        state,
        created=created,
        snapshot=snapshot,
        tool_requested=supported_env.tool_name,
        tool_result=_envelope_dump(supported_env),
        evidence_ids=[supported_eid],
        path=out_path,
        status="retrying" if supported_retries else "running",
        retry_number=supported_retries,
    )

    spec = EvaluateCandidatesSpec(
        model_ids=tuple(proposed),
        frequency=frequency,
        horizon=horizon,
        min_train_size=min_train,
        window_type="expanding",
        step=_backtest_step(int(n), horizon, min_train),
        seed=seed,
        seasonal_period=period,
        seasonality_period=period if period is not None and period >= 1 else 1,
    )
    eval_env, eval_retries = _call_tool(
        EVALUATE_CANDIDATES,
        timestamps=timestamps,
        values=values,
        spec=spec,
        generated_at=created,
    )
    eval_eid = _store_evidence(state, eval_env, next_id)
    _record_step(
        state,
        created=created,
        snapshot=snapshot,
        tool_requested=eval_env.tool_name,
        tool_result=_envelope_dump(eval_env),
        evidence_ids=[eval_eid],
        path=out_path,
        status="retrying" if eval_retries else "running",
        retry_number=eval_retries,
    )

    if not eval_env.ok:
        err_type = "FailedModelExecution"
        msg = eval_env.error_message or "evaluate_candidates failed"
        if eval_env.error_message and "Unsupported" in eval_env.error_message:
            err_type = "UnsupportedModel"
        if eval_env.error_message and "No complete backtest folds" in eval_env.error_message:
            err_type = "InsufficientData"
        return _fail(
            state,
            created=created,
            snapshot=snapshot,
            path=out_path,
            next_id=next_id,
            error_type=err_type,
            error_message=msg,
            extra_eids=[diag_eid, propose_eid, eval_eid],
        )

    rows = _rows_from_payload(eval_env.payload)
    winner, rule = _official_winner(rows)
    report = _synthesize_report(
        diagnostics=diagnostics,
        context=context,
        proposed=proposed,
        rows=rows,
        winner=winner,
        rule=rule,
        diag_eid=diag_eid,
        propose_eid=propose_eid,
        eval_eid=eval_eid,
        supported_eid=supported_eid,
        backtest_executed=bool(eval_env.payload.get("backtest_executed")),
    )
    state.report = report
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
    name: str,
    *,
    timestamps: object,
    values: object,
    spec: EvaluateCandidatesSpec | None,
    generated_at: datetime | None = None,
) -> tuple[ForecastToolEnvelope, int]:
    reject_unknown_forecast_tool(name)
    last_error: Exception | None = None
    for attempt in range(FORECAST_STRATEGIST_MAX_RETRIES + 1):
        try:
            return (
                run_named_forecast_tool(
                    name,
                    timestamps,  # type: ignore[arg-type]
                    values,  # type: ignore[arg-type]
                    spec,
                    generated_at=generated_at,
                ),
                attempt,
            )
        except ForecastInterfaceError as exc:
            return (
                ForecastToolEnvelope(
                    tool_name=name,
                    ok=False,
                    payload={"backtest_executed": False, "summary": str(exc)},
                    error_type="ForecastInterfaceError",
                    error_message=str(exc),
                ),
                attempt,
            )
        except Exception as exc:
            last_error = exc
            if attempt >= FORECAST_STRATEGIST_MAX_RETRIES:
                break
    assert last_error is not None
    return (
        ForecastToolEnvelope(
            tool_name=name,
            ok=False,
            payload={"backtest_executed": False, "summary": str(last_error)},
            error_type=type(last_error).__name__,
            error_message=str(last_error),
        ),
        FORECAST_STRATEGIST_MAX_RETRIES,
    )


def _official_winner(rows: list[CandidateEvalRow]) -> tuple[str | None, SelectionRule]:
    ranked = [row for row in rows if row.rank is not None and row.official_wis is not None]
    ranked.sort(key=lambda row: (row.rank if row.rank is not None else 10**9, row.model_id))
    if not ranked:
        return None, "none"
    return ranked[0].model_id, "official_backtest_wis"


def _rows_from_payload(payload: JsonObject) -> list[CandidateEvalRow]:
    raw = payload.get("candidates") or []
    return [CandidateEvalRow.model_validate(item) for item in raw]


def _synthesize_report(
    *,
    diagnostics: DatasetDiagnostics,
    context: BusinessContext | None,
    proposed: list[str],
    rows: list[CandidateEvalRow],
    winner: str | None,
    rule: SelectionRule,
    diag_eid: str,
    propose_eid: str,
    eval_eid: str,
    supported_eid: str,
    backtest_executed: bool,
) -> ForecastStrategistReport:
    claims: list[CitedClaim] = []
    risks: list[CitedClaim] = []
    investigations: list[InvestigationRecommendation] = []
    used = [diag_eid, propose_eid, supported_eid, eval_eid]

    claims.append(
        CitedClaim(
            kind="observation",
            topic="input",
            statement=_diag_summary(diagnostics),
            evidence_ids=[diag_eid],
            uncertainty="medium",
            why_uncertainty="Diagnostics were supplied by the caller, not re-measured here.",
        )
    )
    claims.append(
        CitedClaim(
            kind="hypothesis",
            topic="candidates",
            statement=(
                "Candidate models " + ", ".join(proposed) + " were shortlisted from diagnostics. "
                "This is not a claim that any of them is superior."
            ),
            evidence_ids=[diag_eid, propose_eid],
            uncertainty="high",
            why_uncertainty="Shortlisting is heuristic; only backtest WIS can rank models.",
        )
    )
    if diagnostics.seasonality_detected is True:
        claims.append(
            CitedClaim(
                kind="observation",
                topic="seasonality",
                statement="Diagnostics flagged seasonality; seasonal candidates were included.",
                evidence_ids=[diag_eid],
                uncertainty="medium",
                why_uncertainty="The flag is reused from diagnostics; it is not a new test.",
            )
        )
    if diagnostics.trend_detected is True:
        claims.append(
            CitedClaim(
                kind="observation",
                topic="trend",
                statement="Diagnostics flagged trend; trend-capable candidates were included.",
                evidence_ids=[diag_eid],
                uncertainty="medium",
                why_uncertainty="The flag is reused from diagnostics; it is not a new test.",
            )
        )
    if diagnostics.structural_break_detected is True:
        risks.append(
            CitedClaim(
                kind="hypothesis",
                topic="structural_change",
                statement=(
                    "A structural-break flag is present. A single global strategy may "
                    "be poorly calibrated if the regime does not persist."
                ),
                evidence_ids=[diag_eid],
                uncertainty="high",
                why_uncertainty="Diagnostics do not say whether the new level continues.",
            )
        )
        investigations.append(
            InvestigationRecommendation(
                action="Review the break time before committing to one strategy.",
                evidence_ids=[diag_eid],
                priority="high",
            )
        )
    if diagnostics.anomalies_detected is True:
        risks.append(
            CitedClaim(
                kind="observation",
                topic="anomalies",
                statement="Anomaly flags exist; backtest WIS may be sensitive to those points.",
                evidence_ids=[diag_eid, eval_eid],
                uncertainty="medium",
                why_uncertainty="Anomaly screens are heuristics; they are not clipped here.",
            )
        )
    if context is not None and context.has_event_column is True:
        claims.append(
            CitedClaim(
                kind="observation",
                topic="context",
                statement=(
                    "An event column was provided by the caller. Labels are not used "
                    "as a superiority argument and no events were invented."
                ),
                evidence_ids=[diag_eid],
                uncertainty="low",
                why_uncertainty="Column presence is caller-supplied metadata only.",
            )
        )
    elif context is None or context.has_event_column is not True:
        claims.append(
            CitedClaim(
                kind="observation",
                topic="context",
                statement="No event column was provided. No business events are inferred.",
                evidence_ids=[diag_eid],
                uncertainty="low",
                why_uncertainty="Absence of metadata is not evidence that events occurred.",
            )
        )

    claims.append(
        CitedClaim(
            kind="observation",
            topic="backtest",
            statement=_comparison_summary(rows),
            evidence_ids=[eval_eid],
            uncertainty="low" if winner is not None else "high",
            why_uncertainty=(
                "WIS values are copied from evaluate_candidates; they are not recomputed."
            ),
        )
    )
    if winner is not None:
        win_row = next(row for row in rows if row.model_id == winner)
        claims.append(
            CitedClaim(
                kind="observation",
                topic="strategy",
                statement=(
                    f"Recommend strategy_id={winner} because it ranked first on official "
                    f"backtest WIS ({win_row.official_wis})."
                ),
                evidence_ids=[eval_eid],
                uncertainty="medium",
                why_uncertainty=(
                    "Official WIS is the measured ranking. It is not a holdout production "
                    "forecast and completed-only means are not used as the headline."
                ),
            )
        )
    else:
        risks.append(
            CitedClaim(
                kind="observation",
                topic="strategy",
                statement=(
                    "No model is claimed superior: official backtest WIS is unavailable "
                    "for every candidate (failed folds or undefined scores)."
                ),
                evidence_ids=[eval_eid],
                uncertainty="high",
                why_uncertainty="Official means are None when any planned fold failed.",
            )
        )
        investigations.append(
            InvestigationRecommendation(
                action="Inspect fold failures and re-run evaluation, or escalate to a human.",
                evidence_ids=[eval_eid],
                priority="high",
            )
        )

    failed_models = [row.model_id for row in rows if row.n_folds_failed]
    if failed_models:
        risks.append(
            CitedClaim(
                kind="observation",
                topic="backtest",
                statement="Failed folds for: " + ", ".join(failed_models) + ".",
                evidence_ids=[eval_eid],
                uncertainty="medium",
                why_uncertainty="Failed folds stay in the record and poison official means.",
            )
        )

    return ForecastStrategistReport(
        proposed_candidate_ids=proposed,
        recommended_strategy_id=winner,
        selection_rule=rule,
        backtest_executed=backtest_executed,
        comparison=rows,
        claims=claims,
        risks=risks,
        investigations=investigations,
        evidence_ids_used=list(dict.fromkeys(used)),
        modified_dataset=False,
        emitted_forecast=False,
    )


def _diag_summary(diagnostics: DatasetDiagnostics) -> str:
    if diagnostics.summary:
        return diagnostics.summary
    parts = [f"n={diagnostics.n_observations}"]
    parts.append(f"trend={diagnostics.trend_detected}")
    parts.append(f"seasonality={diagnostics.seasonality_detected}")
    parts.append(f"anomalies={diagnostics.anomalies_detected}")
    parts.append(f"break={diagnostics.structural_break_detected}")
    return "Diagnostics: " + ", ".join(parts)


def _comparison_summary(rows: list[CandidateEvalRow]) -> str:
    bits: list[str] = []
    for row in rows:
        wis = "None" if row.official_wis is None else f"{row.official_wis:.6g}"
        bits.append(f"{row.model_id} rank={row.rank} official_wis={wis}")
    return "Backtest comparison: " + "; ".join(bits)


def _backtest_step(n: int, horizon: int, min_train_size: int) -> int:
    last = n - 1 - horizon
    first = min_train_size - 1
    if first > last:
        return 1
    n_possible = last - first + 1
    return max(1, (n_possible + 4) // 5)


def _fail(
    state: ForecastStrategistState,
    *,
    created: datetime,
    snapshot: JsonObject,
    path: Path | None,
    next_id: Callable[[], str],
    error_type: str,
    error_message: str,
    extra_eids: list[str] | None = None,
) -> ForecastStrategistState:
    state.status = "failed"
    state.error_type = error_type
    state.error_message = error_message
    state.tool_errors.append(error_message)
    fail_eid = _store_payload(
        state,
        next_id,
        tool_name="strategist_failure",
        payload={"error_type": error_type, "error_message": error_message},
    )
    eids = list(extra_eids or []) + [fail_eid]
    report = ForecastStrategistReport(
        proposed_candidate_ids=[],
        recommended_strategy_id=None,
        selection_rule="none",
        backtest_executed=False,
        comparison=[],
        claims=[
            CitedClaim(
                kind="observation",
                topic="strategy",
                statement=f"No strategy is recommended: {error_message}",
                evidence_ids=eids,
                uncertainty="high",
                why_uncertainty="Evaluation did not produce an official WIS ranking.",
            )
        ],
        risks=[],
        investigations=[
            InvestigationRecommendation(
                action="Resolve the recorded failure before claiming a superior model.",
                evidence_ids=eids,
                priority="high",
            )
        ],
        evidence_ids_used=eids,
        modified_dataset=False,
        emitted_forecast=False,
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
    state: ForecastStrategistState,
    envelope: ForecastToolEnvelope,
    next_id: Callable[[], str],
) -> str:
    return _store_payload(state, next_id, envelope.tool_name, dict(envelope.payload))


def _store_payload(
    state: ForecastStrategistState,
    next_id: Callable[[], str],
    tool_name: str,
    payload: JsonObject,
) -> str:
    eid = next_id()
    state.evidence[eid] = EvidenceItem(evidence_id=eid, tool_name=tool_name, payload=payload)
    return eid


def _envelope_dump(envelope: ForecastToolEnvelope) -> JsonObject:
    return {
        "ok": envelope.ok,
        "error_type": envelope.error_type,
        "error_message": envelope.error_message,
        "payload": envelope.payload,
    }


def _record_step(
    state: ForecastStrategistState,
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
) -> None:
    step = TrajectoryStep(
        run_id=state.run_id,
        agent_id=FORECAST_STRATEGIST_AGENT_ID,
        timestamp=created,
        input_state=snapshot,
        tool_requested=tool_requested,
        tool_result=tool_result,
        decision=decision,
        evidence_ids=evidence_ids,
        retry_number=retry_number,
        final_status=status,  # type: ignore[arg-type]
    )
    state.retry_number = max(state.retry_number, retry_number)
    state.append_step(step)
    persist_trajectory_step(path, step)


def _input_snapshot(
    n_obs: int | None,
    frequency: str | None,
    horizon: int | None,
    seasonal_period: int | None,
) -> JsonObject:
    return {
        "n_observations": n_obs,
        "frequency": frequency,
        "horizon": horizon,
        "seasonal_period": seasonal_period,
        "agent_id": FORECAST_STRATEGIST_AGENT_ID,
        "note": "raw series values are not stored in agent state",
    }


def _evidence_id_factory() -> Callable[[], str]:
    counter = 0

    def _next() -> str:
        nonlocal counter
        counter += 1
        return f"E{counter}"

    return _next
