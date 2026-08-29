"""Forecast Analyst: turn verified artifacts into an evidence-cited narrative.

Repeats numbers only from supplied forecast/verification evidence. Does not fit
models, invent business recommendations, or emit a new yhat. No FastAPI. No LLM.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.agents.context_analyst import ContextAnalystReport
from app.agents.forecast_strategist import DatasetDiagnostics, ForecastStrategistReport
from app.agents.state import (
    FORECAST_ANALYST_AGENT_ID,
    CitedClaim,
    DataDetectiveReport,
    EvidenceItem,
    InvestigationRecommendation,
    TrajectoryStep,
    UncertaintyLevel,
    new_run_id,
)
from app.agents.verifier import VerifierReport
from app.evidence.logger import persist_trajectory_step
from app.forecasting.base import ForecastResult
from app.time_utils import utc_now
from app.tools.verification_tools import ForecastSnapshot, snapshot_from_forecast_result

JsonObject = dict[str, Any]
SectionId = Literal[
    "forecast_summary",
    "expected_forecast",
    "prediction_interval",
    "confidence_quality",
    "model_selected",
    "why_model_selected",
    "historical_patterns",
    "detected_risks",
    "verification_results",
    "context_events",
    "recommended_human_actions",
    "limitations",
]

_REPO_ROOT = Path(__file__).resolve().parents[3]
_TRAJECTORIES_DIR = _REPO_ROOT / "trajectories"

REQUIRED_SECTIONS: tuple[SectionId, ...] = (
    "forecast_summary",
    "expected_forecast",
    "prediction_interval",
    "confidence_quality",
    "model_selected",
    "why_model_selected",
    "historical_patterns",
    "detected_risks",
    "verification_results",
    "context_events",
    "recommended_human_actions",
    "limitations",
)

SECTION_TITLES: dict[SectionId, str] = {
    "forecast_summary": "Forecast summary",
    "expected_forecast": "Expected forecast",
    "prediction_interval": "Prediction interval",
    "confidence_quality": "Confidence/quality assessment",
    "model_selected": "Model selected",
    "why_model_selected": "Why this model was selected",
    "historical_patterns": "Historical patterns",
    "detected_risks": "Detected risks",
    "verification_results": "Verification results",
    "context_events": "Context/events",
    "recommended_human_actions": "Recommended human actions",
    "limitations": "Limitations",
}

_EVENT_TOKENS = (
    "holiday",
    "promotion",
    "promo",
    "campaign",
    "stockout",
    "product launch",
    "price change",
    "product_launch",
    "price_change",
)
_OVERCONFIDENT = (" definitely ", " certainly ", " guaranteed ", " proves ")
_INVENTED_BIZ = (
    "increase inventory",
    "order more",
    "hire additional",
    "raise prices",
    "cut prices",
    "launch a campaign",
)


class ReportSection(BaseModel):
    """One analyst section. Body is narrative; claims carry evidence IDs."""

    model_config = ConfigDict(extra="forbid")

    section_id: SectionId
    title: str
    body: str
    claims: list[CitedClaim]
    evidence_ids: list[str] = Field(min_length=1)
    uncertainty: UncertaintyLevel

    @model_validator(mode="after")
    def section_cites_evidence(self) -> ReportSection:
        if not self.evidence_ids:
            msg = "every section must reference evidence IDs"
            raise ValueError(msg)
        for claim in self.claims:
            if not claim.evidence_ids:
                msg = "every material conclusion must reference evidence IDs"
                raise ValueError(msg)
        return self


class ForecastAnalystReport(BaseModel):
    """Human-readable forecast report. Numbers are copied from artifacts, not invented."""

    model_config = ConfigDict(extra="forbid")

    sections: list[ReportSection]
    markdown: str
    overall_uncertainty: UncertaintyLevel
    context_available: bool
    verification_overall: str | None
    claims: list[CitedClaim]
    risks: list[CitedClaim]
    investigations: list[InvestigationRecommendation]
    evidence_ids_used: list[str]
    modified_dataset: bool = False
    emitted_forecast: bool = False
    forecast_adjusted: bool = False
    invented_business_recommendations: bool = False

    @model_validator(mode="after")
    def report_is_evidence_cited_and_cautious(self) -> ForecastAnalystReport:
        if self.modified_dataset:
            msg = "Forecast Analyst must not modify the dataset"
            raise ValueError(msg)
        if self.emitted_forecast or self.forecast_adjusted:
            msg = "Forecast Analyst must not emit or adjust a numerical forecast"
            raise ValueError(msg)
        if self.invented_business_recommendations:
            msg = "Forecast Analyst must not invent business recommendations"
            raise ValueError(msg)
        ids = [item.section_id for item in self.sections]
        if tuple(ids) != REQUIRED_SECTIONS:
            msg = "report must contain the twelve required sections in order"
            raise ValueError(msg)
        blob = " ".join(item.body for item in self.sections).lower()
        padded = f" {blob} "
        if any(token in padded for token in _OVERCONFIDENT):
            msg = "report must not use overconfident language"
            raise ValueError(msg)
        if any(phrase in blob for phrase in _INVENTED_BIZ):
            msg = "report must not invent unsupported business recommendations"
            raise ValueError(msg)
        if not self.context_available:
            for token in _EVENT_TOKENS:
                if token in blob:
                    msg = "must not invent business events when context is unavailable"
                    raise ValueError(msg)
        for claim in (*self.claims, *self.risks):
            if not claim.evidence_ids:
                msg = "every material conclusion must reference evidence IDs"
                raise ValueError(msg)
        for section in self.sections:
            for eid in section.evidence_ids:
                if eid not in self.evidence_ids_used:
                    msg = f"section {section.section_id} cites unknown evidence {eid}"
                    raise ValueError(msg)
        return self


class ForecastAnalystState(BaseModel):
    """Explicit Forecast Analyst state. Training series values are not stored."""

    model_config = ConfigDict(extra="forbid")

    run_id: str
    agent_id: str = FORECAST_ANALYST_AGENT_ID
    status: str
    evidence: dict[str, EvidenceItem] = Field(default_factory=dict)
    tool_errors: list[str] = Field(default_factory=list)
    report: ForecastAnalystReport | None = None
    retry_number: int = 0
    trajectory: list[TrajectoryStep] = Field(default_factory=list)
    error_type: str | None = None
    error_message: str | None = None

    def append_step(self, step: TrajectoryStep) -> None:
        self.trajectory.append(step)


def run_forecast_analyst(
    *,
    forecast: ForecastSnapshot | ForecastResult | None,
    verifier_report: VerifierReport | None = None,
    strategist_report: ForecastStrategistReport | None = None,
    detective_report: DataDetectiveReport | None = None,
    context_report: ContextAnalystReport | None = None,
    diagnostics: DatasetDiagnostics | None = None,
    run_id: str | None = None,
    generated_at: datetime | None = None,
    trajectory_path: Path | None = None,
    persist_trajectory: bool = True,
) -> ForecastAnalystState:
    """Compile a twelve-section report from supplied artifacts.

    Does not re-fit models. Does not invent events or business actions.
    """
    created = generated_at if generated_at is not None else utc_now()
    rid = run_id if run_id is not None else new_run_id(created, prefix="forecast-analyst")
    state = ForecastAnalystState(run_id=rid, status="running", retry_number=0)
    out_path = trajectory_path
    if persist_trajectory and out_path is None:
        out_path = _TRAJECTORIES_DIR / f"{rid}.jsonl"
    if out_path is not None:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text("", encoding="utf-8", newline="\n")

    snapshot = _input_snapshot(forecast, verifier_report, context_report)
    next_id = _evidence_id_factory()

    if forecast is None or (
        not isinstance(forecast, ForecastResult) and not getattr(forecast, "yhat", None)
    ):
        return _fail(
            state,
            created=created,
            snapshot=snapshot,
            path=out_path,
            next_id=next_id,
            extra_eids=[],
            error_type="MissingForecast",
            error_message="Forecast Analyst requires a verified forecast artifact.",
        )

    snap = (
        snapshot_from_forecast_result(forecast)
        if isinstance(forecast, ForecastResult)
        else forecast
    )
    fc_eid = _store_payload(state, next_id, "forecast_artifact", snap.model_dump(mode="json"))
    _record_step(
        state,
        created=created,
        snapshot=snapshot,
        tool_requested=None,
        tool_result=None,
        evidence_ids=[fc_eid],
        path=out_path,
        status="running",
        decision={"note": "Forecast values are copied from the artifact, not recomputed."},
    )
    ver_eid = _store_optional(state, next_id, "verifier_report", verifier_report)
    strat_eid = _store_optional(state, next_id, "strategist_report", strategist_report)
    det_eid = _store_optional(state, next_id, "detective_report", detective_report)
    ctx_eid = _store_optional(state, next_id, "context_report", context_report)
    diag_eid = _store_optional(state, next_id, "diagnostics_input", diagnostics)
    for eid in (ver_eid, strat_eid, det_eid, ctx_eid, diag_eid):
        if eid is None:
            continue
        _record_step(
            state,
            created=created,
            snapshot=snapshot,
            tool_requested=None,
            tool_result=None,
            evidence_ids=[eid],
            path=out_path,
            status="running",
        )

    report = _synthesize_report(
        snap=snap,
        fc_eid=fc_eid,
        verifier_report=verifier_report,
        ver_eid=ver_eid,
        strategist_report=strategist_report,
        strat_eid=strat_eid,
        detective_report=detective_report,
        det_eid=det_eid,
        context_report=context_report,
        ctx_eid=ctx_eid,
        diagnostics=diagnostics,
        diag_eid=diag_eid,
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


def _synthesize_report(
    *,
    snap: ForecastSnapshot,
    fc_eid: str,
    verifier_report: VerifierReport | None,
    ver_eid: str | None,
    strategist_report: ForecastStrategistReport | None,
    strat_eid: str | None,
    detective_report: DataDetectiveReport | None,
    det_eid: str | None,
    context_report: ContextAnalystReport | None,
    ctx_eid: str | None,
    diagnostics: DatasetDiagnostics | None,
    diag_eid: str | None,
) -> ForecastAnalystReport:
    context_available = bool(context_report is not None and context_report.context_available)
    fallback = fc_eid
    sections = [
        _section_summary(snap, fc_eid, ver_eid, verifier_report),
        _section_expected(snap, fc_eid),
        _section_interval(snap, fc_eid),
        _section_quality(verifier_report, ver_eid, fallback),
        _section_model(snap, fc_eid, strategist_report, strat_eid),
        _section_why(strategist_report, strat_eid, fc_eid),
        _section_history(diagnostics, diag_eid, detective_report, det_eid, fallback),
        _section_risks(
            verifier_report,
            ver_eid,
            strategist_report,
            strat_eid,
            detective_report,
            det_eid,
            fallback,
        ),
        _section_verification(verifier_report, ver_eid, fallback),
        _section_context(context_report, ctx_eid, fallback),
        _section_actions(
            verifier_report,
            ver_eid,
            strategist_report,
            detective_report,
            context_report,
            fallback,
            context_available,
        ),
        _section_limitations(fc_eid, ver_eid, strat_eid, det_eid, ctx_eid, context_available),
    ]
    claims: list[CitedClaim] = []
    risks: list[CitedClaim] = []
    for section in sections:
        claims.extend(section.claims)
        if section.section_id == "detected_risks":
            risks.extend(section.claims)
    used: list[str] = []
    for section in sections:
        used.extend(section.evidence_ids)
    investigations = _investigations_from_inputs(
        verifier_report,
        strategist_report,
        detective_report,
        context_report,
        fallback,
        context_available,
    )
    verification_overall = None if verifier_report is None else verifier_report.overall_reported
    return ForecastAnalystReport(
        sections=sections,
        markdown=_render_markdown(sections),
        overall_uncertainty=_overall_uncertainty(verifier_report, strategist_report),
        context_available=context_available,
        verification_overall=verification_overall,
        claims=claims,
        risks=risks,
        investigations=investigations,
        evidence_ids_used=list(dict.fromkeys(used)),
        modified_dataset=False,
        emitted_forecast=False,
        forecast_adjusted=False,
        invented_business_recommendations=False,
    )


def _claim(
    *,
    topic: str,
    statement: str,
    evidence_ids: list[str],
    uncertainty: UncertaintyLevel,
    why: str,
) -> CitedClaim:
    return CitedClaim(
        kind="observation",
        topic=topic,  # type: ignore[arg-type]
        statement=statement,
        evidence_ids=evidence_ids,
        uncertainty=uncertainty,
        why_uncertainty=why,
    )


def _pack(
    section_id: SectionId,
    body: str,
    claims: list[CitedClaim],
    evidence_ids: list[str],
    uncertainty: UncertaintyLevel,
) -> ReportSection:
    return ReportSection(
        section_id=section_id,
        title=SECTION_TITLES[section_id],
        body=body,
        claims=claims,
        evidence_ids=list(dict.fromkeys(evidence_ids)),
        uncertainty=uncertainty,
    )


def _section_summary(
    snap: ForecastSnapshot,
    fc_eid: str,
    ver_eid: str | None,
    verifier_report: VerifierReport | None,
) -> ReportSection:
    model = snap.model or "unspecified"
    eids = [fc_eid]
    uncertainty: UncertaintyLevel = "high"
    verify_bit = "Verification results were not provided."
    if verifier_report is not None and ver_eid is not None:
        eids.append(ver_eid)
        verify_bit = (
            f"Deterministic verification overall result is {verifier_report.overall_reported}."
        )
        uncertainty = "medium" if verifier_report.overall_reported == "PASS" else "high"
    body = (
        f"This report restates a {model} forecast of horizon {snap.forecast_horizon} "
        f"at frequency {snap.frequency}. Point values and intervals are copied from the "
        f"forecast artifact (evidence {fc_eid}); they were not recomputed. {verify_bit} "
        "This summary is not a claim that the forecast is known to be accurate."
    )
    claim = _claim(
        topic="report",
        statement=body,
        evidence_ids=eids,
        uncertainty=uncertainty,
        why="The analyst restates artifacts; it does not generate a new forecast.",
    )
    return _pack("forecast_summary", body, [claim], eids, uncertainty)


def _section_expected(snap: ForecastSnapshot, fc_eid: str) -> ReportSection:
    body = (
        "Expected point forecast copied from the forecast artifact "
        f"(evidence {fc_eid}): {_fmt_values(snap.yhat)}. "
        "These values were not invented or adjusted by the analyst."
    )
    claim = _claim(
        topic="report",
        statement=body,
        evidence_ids=[fc_eid],
        uncertainty="low",
        why="Values are copied from the supplied artifact.",
    )
    return _pack("expected_forecast", body, [claim], [fc_eid], "low")


def _section_interval(snap: ForecastSnapshot, fc_eid: str) -> ReportSection:
    nominal = snap.interval_coverage_nominal
    nom_txt = "unspecified nominal coverage" if nominal is None else f"nominal coverage {nominal}"
    body = (
        f"Prediction interval ({nom_txt}) copied from the forecast artifact "
        f"(evidence {fc_eid}): lower={_fmt_values(snap.lower)}; "
        f"upper={_fmt_values(snap.upper)}. Interval quality is scored separately from "
        "point values and is not implied by this listing."
    )
    claim = _claim(
        topic="report",
        statement=body,
        evidence_ids=[fc_eid],
        uncertainty="low",
        why="Bounds are copied from the supplied artifact.",
    )
    return _pack("prediction_interval", body, [claim], [fc_eid], "low")


def _section_quality(
    verifier_report: VerifierReport | None,
    ver_eid: str | None,
    fallback: str,
) -> ReportSection:
    if verifier_report is None or ver_eid is None:
        body = (
            "Confidence/quality assessment is uncertain: verification results were not "
            "provided. The forecast should not be treated as confirmed."
        )
        claim = _claim(
            topic="verification",
            statement=body,
            evidence_ids=[fallback],
            uncertainty="high",
            why="No verifier report was supplied.",
        )
        return _pack("confidence_quality", body, [claim], [fallback], "high")
    overall = verifier_report.overall_reported
    if overall == "FAIL":
        body = (
            f"Quality is not confirmed. Deterministic verification overall result is FAIL "
            f"(evidence {ver_eid}). Failed checks challenge the artifact; they were not "
            "overridden by this analyst."
        )
        uncertainty: UncertaintyLevel = "high"
    elif overall == "WARN":
        body = (
            f"Quality is uncertain. Deterministic verification overall result is WARN "
            f"(evidence {ver_eid}). Some properties could not be confirmed."
        )
        uncertainty = "high"
    else:
        body = (
            f"Deterministic verification did not falsify the artifact (overall PASS, "
            f"evidence {ver_eid}). That is not a guarantee of accuracy on unseen outcomes."
        )
        uncertainty = "medium"
    claim = _claim(
        topic="verification",
        statement=body,
        evidence_ids=[ver_eid],
        uncertainty=uncertainty,
        why="Quality is taken from verifier results, not from narrative confidence.",
    )
    return _pack("confidence_quality", body, [claim], [ver_eid], uncertainty)


def _section_model(
    snap: ForecastSnapshot,
    fc_eid: str,
    strategist_report: ForecastStrategistReport | None,
    strat_eid: str | None,
) -> ReportSection:
    artifact_model = snap.model or "unspecified"
    eids = [fc_eid]
    extra = ""
    uncertainty: UncertaintyLevel = "medium"
    if strategist_report is not None and strat_eid is not None:
        eids.append(strat_eid)
        rec = strategist_report.recommended_strategy_id
        if rec is None:
            extra = " The strategist did not claim a superior model from official backtest WIS."
            uncertainty = "high"
        elif rec != artifact_model:
            extra = (
                f" The strategist recommended {rec}, which does not match the artifact "
                "model id. This mismatch is recorded; the analyst does not choose a winner."
            )
            uncertainty = "high"
        else:
            extra = f" The strategist recommended the same strategy_id={rec}."
            uncertainty = "low"
    body = (
        f"The forecast artifact names model {artifact_model} (evidence {fc_eid}).{extra} "
        "The analyst did not select a model."
    )
    claim = _claim(
        topic="strategy",
        statement=body,
        evidence_ids=eids,
        uncertainty=uncertainty,
        why="Model identity is copied from artifacts, not chosen here.",
    )
    return _pack("model_selected", body, [claim], eids, uncertainty)


def _section_why(
    strategist_report: ForecastStrategistReport | None,
    strat_eid: str | None,
    fc_eid: str,
) -> ReportSection:
    if strategist_report is None or strat_eid is None:
        body = (
            "Why this model was selected is unavailable: no strategist backtest ranking "
            "was supplied. The artifact model id is not treated as proven superiority."
        )
        claim = _claim(
            topic="strategy",
            statement=body,
            evidence_ids=[fc_eid],
            uncertainty="high",
            why="Selection rationale requires official backtest WIS evidence.",
        )
        return _pack("why_model_selected", body, [claim], [fc_eid], "high")
    rec = strategist_report.recommended_strategy_id
    if rec is None or not strategist_report.backtest_executed:
        body = (
            "No model is described as superior. Official backtest WIS ranking was not "
            f"available as a winner (evidence {strat_eid})."
        )
        uncertainty: UncertaintyLevel = "high"
    elif strategist_report.selection_rule != "official_backtest_wis":
        body = (
            "A strategy id is present but the recorded selection rule is not official "
            f"backtest WIS (evidence {strat_eid}). Superiority is not asserted."
        )
        uncertainty = "high"
    else:
        bits = []
        for row in strategist_report.comparison:
            wis = "None" if row.official_wis is None else f"{row.official_wis:.6g}"
            bits.append(f"{row.model_id} rank={row.rank} official_wis={wis}")
        body = (
            f"Strategy {rec} was recommended because it ranked first on official backtest "
            f"WIS (evidence {strat_eid}). Comparison: " + "; ".join(bits) + ". "
            "Completed-only means are not used as the headline."
        )
        uncertainty = "medium"
    claim = _claim(
        topic="backtest",
        statement=body,
        evidence_ids=[strat_eid],
        uncertainty=uncertainty,
        why="WIS values are restated from the strategist comparison, not recomputed.",
    )
    return _pack("why_model_selected", body, [claim], [strat_eid], uncertainty)


def _section_history(
    diagnostics: DatasetDiagnostics | None,
    diag_eid: str | None,
    detective_report: DataDetectiveReport | None,
    det_eid: str | None,
    fallback: str,
) -> ReportSection:
    eids: list[str] = []
    parts: list[str] = []
    if diagnostics is not None and diag_eid is not None:
        eids.append(diag_eid)
        parts.append(
            "Caller diagnostics: "
            f"trend={diagnostics.trend_detected}, "
            f"seasonality={diagnostics.seasonality_detected}, "
            f"anomalies={diagnostics.anomalies_detected}, "
            f"structural_break={diagnostics.structural_break_detected}, "
            f"n={diagnostics.n_observations}."
        )
        if diagnostics.summary:
            parts.append(diagnostics.summary)
    if detective_report is not None and det_eid is not None:
        eids.append(det_eid)
        parts.append(
            f"Data Detective forecastability={detective_report.forecastability} "
            f"(evidence {det_eid})."
        )
        for item in detective_report.claims:
            if item.topic in {"trend", "seasonality", "anomalies", "structural_change"}:
                parts.append(item.statement)
    if not parts:
        body = (
            "Historical pattern diagnostics were not provided. No trend, seasonality, "
            "or break is inferred."
        )
        eids = [fallback]
        uncertainty: UncertaintyLevel = "high"
    else:
        body = (
            "Historical patterns restated from supplied diagnostics; they were not "
            "re-screened. " + " ".join(parts)
        )
        uncertainty = "medium"
        eids = list(dict.fromkeys(eids))
    claim = _claim(
        topic="input",
        statement=body,
        evidence_ids=eids,
        uncertainty=uncertainty,
        why="Patterns are restated from caller diagnostics, not newly measured.",
    )
    return _pack("historical_patterns", body, [claim], eids, uncertainty)


def _section_risks(
    verifier_report: VerifierReport | None,
    ver_eid: str | None,
    strategist_report: ForecastStrategistReport | None,
    strat_eid: str | None,
    detective_report: DataDetectiveReport | None,
    det_eid: str | None,
    fallback: str,
) -> ReportSection:
    eids: list[str] = []
    lines: list[str] = []
    if verifier_report is not None and ver_eid is not None:
        eids.append(ver_eid)
        for check in verifier_report.reported_checks:
            if check.result in {"FAIL", "WARN"}:
                lines.append(f"{check.check_id} {check.result}: {check.explanation}")
        for risk in verifier_report.risks:
            lines.append(risk.statement)
    if strategist_report is not None and strat_eid is not None:
        eids.append(strat_eid)
        for risk in strategist_report.risks:
            lines.append(risk.statement)
    if detective_report is not None and det_eid is not None:
        eids.append(det_eid)
        for risk in detective_report.risks:
            lines.append(risk.statement)
    eids = list(dict.fromkeys(eids)) or [fallback]
    if not lines:
        body = "No additional risks were recorded in the supplied evidence."
        uncertainty: UncertaintyLevel = "medium"
    else:
        body = "Detected risks copied from supplied reports: " + " ".join(lines)
        uncertainty = "high" if any("FAIL" in line for line in lines) else "medium"
    claim = _claim(
        topic="investigation",
        statement=body,
        evidence_ids=eids,
        uncertainty=uncertainty,
        why="Risks are restated from other agents, not newly tested.",
    )
    return _pack("detected_risks", body, [claim], eids, uncertainty)


def _section_verification(
    verifier_report: VerifierReport | None,
    ver_eid: str | None,
    fallback: str,
) -> ReportSection:
    if verifier_report is None or ver_eid is None:
        body = (
            "Verification results are unavailable: no verifier report was supplied. "
            "Checks were not assumed to have passed."
        )
        claim = _claim(
            topic="verification",
            statement=body,
            evidence_ids=[fallback],
            uncertainty="high",
            why="Missing verification is not treated as a pass.",
        )
        return _pack("verification_results", body, [claim], [fallback], "high")
    bits = [f"{item.check_id}={item.result}" for item in verifier_report.reported_checks]
    body = (
        f"Verification overall={verifier_report.overall_reported} "
        f"(deterministic overall={verifier_report.overall_deterministic}, "
        f"evidence {ver_eid}). Checks: " + "; ".join(bits) + ". "
        "The analyst did not change these results."
    )
    uncertainty: UncertaintyLevel = "high"
    if verifier_report.overall_reported == "PASS":
        uncertainty = "low"
    claim = _claim(
        topic="verification",
        statement=body,
        evidence_ids=[ver_eid],
        uncertainty=uncertainty,
        why="Results are copied from the verifier; they are not reinterpreted.",
    )
    return _pack("verification_results", body, [claim], [ver_eid], uncertainty)


def _section_context(
    context_report: ContextAnalystReport | None,
    ctx_eid: str | None,
    fallback: str,
) -> ReportSection:
    if context_report is None or ctx_eid is None:
        body = (
            "Contextual analysis is unavailable: no context/event report was supplied. "
            "No business events are inferred."
        )
        claim = _claim(
            topic="context",
            statement=body,
            evidence_ids=[fallback],
            uncertainty="low",
            why="Absence of context is observed; events are not invented.",
        )
        return _pack("context_events", body, [claim], [fallback], "low")
    if not context_report.context_available:
        reason = context_report.unavailable_reason or (
            "No context or event data was provided. Contextual analysis is unavailable."
        )
        body = reason + " No business events are inferred."
        claim = _claim(
            topic="context",
            statement=body,
            evidence_ids=[ctx_eid],
            uncertainty="low",
            why="The context agent reported that analysis is unavailable.",
        )
        return _pack("context_events", body, [claim], [ctx_eid], "low")
    facts = [item.statement for item in context_report.observed_facts]
    hyps = [item.statement for item in context_report.possible_explanations]
    body = "Observed context facts: " + " ".join(facts)
    if hyps:
        body += " Possible explanations (not causal findings): " + " ".join(hyps)
    claim = _claim(
        topic="context",
        statement=body,
        evidence_ids=[ctx_eid],
        uncertainty="medium",
        why="Labels are restated; causality is not identified.",
    )
    return _pack("context_events", body, [claim], [ctx_eid], "medium")


def _section_actions(
    verifier_report: VerifierReport | None,
    ver_eid: str | None,
    strategist_report: ForecastStrategistReport | None,
    detective_report: DataDetectiveReport | None,
    context_report: ContextAnalystReport | None,
    fallback: str,
    context_available: bool,
) -> ReportSection:
    actions = _investigations_from_inputs(
        verifier_report,
        strategist_report,
        detective_report,
        context_report,
        fallback,
        context_available,
    )
    eids = list(dict.fromkeys(eid for item in actions for eid in item.evidence_ids)) or [fallback]
    if ver_eid is not None:
        eids = list(dict.fromkeys([*eids, ver_eid]))
    if not actions:
        body = "No additional human action was required by the supplied evidence."
        uncertainty: UncertaintyLevel = "medium"
        claims = [
            _claim(
                topic="investigation",
                statement=body,
                evidence_ids=eids,
                uncertainty=uncertainty,
                why="No supplied investigation list was present.",
            )
        ]
    else:
        body = "Recommended human actions copied from supplied evidence: " + " ".join(
            item.action for item in actions
        )
        uncertainty = "high" if any(item.priority == "high" for item in actions) else "medium"
        claims = [
            _claim(
                topic="investigation",
                statement=item.action,
                evidence_ids=item.evidence_ids,
                uncertainty=uncertainty,
                why="Actions are copied from other agents; none were invented here.",
            )
            for item in actions
        ]
    return _pack("recommended_human_actions", body, claims, eids, uncertainty)


def _section_limitations(
    fc_eid: str,
    ver_eid: str | None,
    strat_eid: str | None,
    det_eid: str | None,
    ctx_eid: str | None,
    context_available: bool,
) -> ReportSection:
    eids = [fc_eid]
    for eid in (ver_eid, strat_eid, det_eid, ctx_eid):
        if eid is not None:
            eids.append(eid)
    missing: list[str] = []
    if ver_eid is None:
        missing.append("verification")
    if strat_eid is None:
        missing.append("model-selection rationale")
    if det_eid is None:
        missing.append("detective diagnostics")
    if not context_available:
        missing.append("context/events")
    miss_txt = (
        " Missing inputs: " + ", ".join(missing) + "."
        if missing
        else " All optional supporting reports were supplied."
    )
    body = (
        "Limitations: the analyst restates artifacts and does not re-fit models, recompute "
        "metrics, or adjust yhat. PASS on verification does not prove future accuracy. "
        "Point accuracy and interval quality are separate. Context labels are not causes. "
        f"Business actions that were not in the supplied evidence were not added.{miss_txt}"
    )
    claim = _claim(
        topic="report",
        statement=body,
        evidence_ids=eids,
        uncertainty="low",
        why="Limitations describe missing inputs and method bounds, not outcomes.",
    )
    return _pack("limitations", body, [claim], eids, "low")


def _investigations_from_inputs(
    verifier_report: VerifierReport | None,
    strategist_report: ForecastStrategistReport | None,
    detective_report: DataDetectiveReport | None,
    context_report: ContextAnalystReport | None,
    fallback: str,
    context_available: bool,
) -> list[InvestigationRecommendation]:
    out: list[InvestigationRecommendation] = []
    if verifier_report is not None:
        out.extend(verifier_report.investigations)
    else:
        out.append(
            InvestigationRecommendation(
                action=(
                    "Run deterministic verification before relying on this forecast; "
                    "verification was not provided."
                ),
                evidence_ids=[fallback],
                priority="high",
            )
        )
    if strategist_report is not None:
        out.extend(strategist_report.investigations)
    if detective_report is not None:
        out.extend(detective_report.investigations)
    if context_report is not None:
        out.extend(context_report.investigations)
    cleaned: list[InvestigationRecommendation] = []
    for item in out:
        text = item.action.lower()
        if any(phrase in text for phrase in _INVENTED_BIZ):
            continue
        if not context_available and any(token in text for token in _EVENT_TOKENS):
            continue
        cleaned.append(
            InvestigationRecommendation(
                action=item.action,
                evidence_ids=[fallback],
                priority=item.priority,
            )
        )
    return cleaned


def _overall_uncertainty(
    verifier_report: VerifierReport | None,
    strategist_report: ForecastStrategistReport | None,
) -> UncertaintyLevel:
    if verifier_report is None:
        return "high"
    if verifier_report.overall_reported != "PASS":
        return "high"
    if strategist_report is None or strategist_report.recommended_strategy_id is None:
        return "high"
    return "medium"


def _render_markdown(sections: list[ReportSection]) -> str:
    parts: list[str] = []
    for index, section in enumerate(sections, start=1):
        parts.append(f"## {index}. {section.title}\n\n{section.body}")
    return "\n\n".join(parts)


def _fmt_values(values: list[float]) -> str:
    return "[" + ", ".join(f"{item:.6g}" for item in values) + "]"


def _store_optional(
    state: ForecastAnalystState,
    next_id: Callable[[], str],
    tool_name: str,
    payload: BaseModel | None,
) -> str | None:
    if payload is None:
        return None
    return _store_payload(state, next_id, tool_name, payload.model_dump(mode="json"))


def _fail(
    state: ForecastAnalystState,
    *,
    created: datetime,
    snapshot: JsonObject,
    path: Path | None,
    next_id: Callable[[], str],
    extra_eids: list[str],
    error_type: str,
    error_message: str,
) -> ForecastAnalystState:
    state.status = "failed"
    state.error_type = error_type
    state.error_message = error_message
    state.tool_errors.append(error_message)
    fail_eid = _store_payload(
        state,
        next_id,
        tool_name="forecast_analyst_failure",
        payload={"error_type": error_type, "error_message": error_message},
    )
    eids = list(extra_eids) + [fail_eid]
    claim = _claim(
        topic="report",
        statement=error_message,
        evidence_ids=eids,
        uncertainty="high",
        why="No forecast artifact was available to restate.",
    )
    body = (
        error_message + " Contextual analysis is unavailable in this failed run. "
        "No business events are inferred."
    )
    sections = [_pack(section_id, body, [claim], eids, "high") for section_id in REQUIRED_SECTIONS]
    report = ForecastAnalystReport(
        sections=sections,
        markdown=_render_markdown(sections),
        overall_uncertainty="high",
        context_available=False,
        verification_overall=None,
        claims=[claim],
        risks=[],
        investigations=[
            InvestigationRecommendation(
                action="Supply a forecast artifact, then re-run the analyst.",
                evidence_ids=eids,
                priority="high",
            )
        ],
        evidence_ids_used=eids,
        modified_dataset=False,
        emitted_forecast=False,
        forecast_adjusted=False,
        invented_business_recommendations=False,
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


def _store_payload(
    state: ForecastAnalystState,
    next_id: Callable[[], str],
    tool_name: str,
    payload: JsonObject,
) -> str:
    eid = next_id()
    state.evidence[eid] = EvidenceItem(evidence_id=eid, tool_name=tool_name, payload=payload)
    return eid


def _record_step(
    state: ForecastAnalystState,
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
        agent_id=FORECAST_ANALYST_AGENT_ID,
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
    forecast: ForecastSnapshot | ForecastResult | None,
    verifier_report: VerifierReport | None,
    context_report: ContextAnalystReport | None,
) -> JsonObject:
    n_fc = None
    model = None
    if isinstance(forecast, ForecastResult):
        n_fc = len(forecast.yhat)
        model = forecast.model
    elif isinstance(forecast, ForecastSnapshot):
        n_fc = len(forecast.yhat)
        model = forecast.model
    return {
        "n_forecast": n_fc,
        "model": model,
        "has_verifier": verifier_report is not None,
        "has_context": context_report is not None,
        "agent_id": FORECAST_ANALYST_AGENT_ID,
        "note": "training series values are not stored in agent state",
    }


def _evidence_id_factory() -> Callable[[], str]:
    counter = 0

    def _next() -> str:
        nonlocal counter
        counter += 1
        return f"E{counter}"

    return _next
