"""Agent run HTTP adapter. Starts the graph in a background task; does not block."""

from __future__ import annotations

import json
import logging
from datetime import datetime

from fastapi import APIRouter, BackgroundTasks, Depends, Request

from app.agents.checkpoint import (
    CheckpointDecisionError,
    HumanCheckpoint,
    apply_human_checkpoint,
)
from app.agents.orchestrator import OrchestratorState, run_orchestrator
from app.api.deps import get_store
from app.api.errors import ApiError
from app.api.ids import new_prefixed_id, require_resource_id
from app.api.job_limit import acquire_background_job, release_background_job
from app.api.schemas import (
    CandidateRowView,
    CheckpointDecisionRequest,
    ClaimView,
    HumanCheckpointView,
    RunCreateRequest,
    RunErrorView,
    RunResponse,
    TrajectoryResponse,
    TrajectoryStepView,
    VerificationCheckView,
)
from app.api.series_io import load_dataset_frame, resolve_frequency, series_columns
from app.api.store import FileStore
from app.evidence.logger import persist_trajectory_step
from app.forecasting.base import ForecastResult
from app.request_context import set_request_id
from app.time_utils import utc_now

router = APIRouter(tags=["runs"])
logger = logging.getLogger(__name__)


def _checkpoint_view(value: HumanCheckpoint | None) -> HumanCheckpointView | None:
    if value is None:
        return None
    return HumanCheckpointView.model_validate(value.model_dump())


def _checkpoint_domain(value: HumanCheckpointView | None) -> HumanCheckpoint | None:
    if value is None:
        return None
    return HumanCheckpoint.model_validate(value.model_dump())


def _forecast_from_state(state: OrchestratorState) -> ForecastResult | None:
    forecast = state.forecast
    if isinstance(forecast, ForecastResult):
        return forecast
    return None


def _attach_run_evidence(record: RunResponse, state: OrchestratorState) -> None:
    strategist = state.strategist_report
    if strategist is not None:
        record.candidates = [
            CandidateRowView.model_validate(row.model_dump()) for row in strategist.comparison
        ]
    verifier = state.verifier_report
    if verifier is not None:
        record.verification_checks = [
            VerificationCheckView(
                check_id=item.check_id,
                name=item.name,
                result=item.result,
                severity=item.severity,
                explanation=item.explanation,
                applicable=item.applicable,
            )
            for item in verifier.deterministic_checks
        ]
    analyst = state.analyst_report
    risks = []
    if analyst is not None:
        risks = analyst.risks
        record.evidence_ids = list(analyst.evidence_ids_used)
        record.overall_uncertainty = analyst.overall_uncertainty
        record.analysis_markdown = analyst.markdown
    elif verifier is not None:
        risks = verifier.risks
        record.evidence_ids = list(verifier.evidence_ids_used)
    elif strategist is not None:
        risks = strategist.risks
        record.evidence_ids = list(strategist.evidence_ids_used)
    record.risks = [
        ClaimView(
            kind=item.kind,
            topic=item.topic,
            statement=item.statement,
            evidence_ids=list(item.evidence_ids),
            uncertainty=item.uncertainty,
        )
        for item in risks
    ]


def execute_run(store: FileStore, run_id: str, request_id: str | None) -> None:
    """Background worker. Failures are stored as public errors; traces stay in logs."""
    try:
        set_request_id(request_id)
        record = store.get_run(run_id)
        record.status = "running"
        record.started_at = utc_now()
        store.put_run(record)
        try:
            _dataset, frame = load_dataset_frame(store, record.dataset_id)
            timestamps, values, events, context = series_columns(frame)
            traj_path = store.trajectory_path(run_id)
            state = run_orchestrator(
                timestamps,
                values,
                horizon=record.horizon,
                frequency=record.frequency,
                event_labels=events,
                context_labels=context,
                seed=record.seed,
                coverage=record.coverage,
                seasonal_period=record.seasonal_period,
                run_id=run_id,
                trajectory_path=traj_path,
                persist_trajectory=True,
            )
            record.status = state.status
            record.finished_at = utc_now()
            record.retry_number = state.retry_number
            record.selected_strategy_id = state.selected_strategy_id
            record.verification_overall = state.verification_overall
            record.accepted = state.accepted
            record.review_required = state.review_required
            record.nodes_visited = list(state.nodes_visited)
            record.human_checkpoint = _checkpoint_view(state.human_checkpoint)
            record.forecast = _forecast_from_state(state)
            record.trajectory_available = traj_path.is_file() and traj_path.stat().st_size > 0
            _attach_run_evidence(record, state)
            if state.error_type or state.status == "failed":
                record.error = RunErrorView(
                    error_code=state.error_type or "run_failed",
                    message=state.error_message or "The agent run failed.",
                )
            logger.info(
                "run_finished",
                extra={
                    "event": "run_finished",
                    "run_id": run_id,
                    "status": record.status,
                    "retry_number": record.retry_number,
                    "strategy_id": record.selected_strategy_id,
                },
            )
        except ApiError as exc:
            record.status = "failed"
            record.finished_at = utc_now()
            record.error = RunErrorView(error_code=exc.error_code, message=exc.message)
            logger.info(
                "run_failed",
                extra={"event": "run_failed", "run_id": run_id, "error_code": exc.error_code},
            )
        except Exception:
            logger.exception("run_failed", extra={"event": "run_failed", "run_id": run_id})
            record.status = "failed"
            record.finished_at = utc_now()
            record.error = RunErrorView(
                error_code="internal_error",
                message="The agent run failed.",
            )
        store.put_run(record)
    finally:
        release_background_job()
        set_request_id(None)


@router.post("/runs", response_model=RunResponse, status_code=202)
def create_run(
    body: RunCreateRequest,
    background: BackgroundTasks,
    request: Request,
    store: FileStore = Depends(get_store),
) -> RunResponse:
    require_resource_id(body.dataset_id)
    dataset, _frame = load_dataset_frame(store, body.dataset_id)
    frequency = resolve_frequency(dataset, body.frequency)
    run_id = new_prefixed_id("run")
    record = RunResponse(
        id=run_id,
        dataset_id=body.dataset_id,
        status="queued",
        created_at=utc_now(),
        horizon=body.horizon,
        frequency=frequency,
        coverage=body.coverage,
        seed=body.seed,
        seasonal_period=body.seasonal_period,
        trajectory_available=False,
    )
    acquire_background_job()
    try:
        store.put_run(record)
    except Exception:
        release_background_job()
        raise
    request_id = getattr(request.state, "request_id", None)
    background.add_task(execute_run, store, run_id, request_id)
    logger.info(
        "run_queued",
        extra={
            "event": "run_queued",
            "run_id": run_id,
            "dataset_id": body.dataset_id,
            "horizon": body.horizon,
            "frequency": frequency,
        },
    )
    return record


@router.get("/runs/{run_id}", response_model=RunResponse)
def get_run(run_id: str, store: FileStore = Depends(get_store)) -> RunResponse:
    require_resource_id(run_id)
    record = store.get_run(run_id)
    logger.info("run_fetched", extra={"event": "run_fetched", "run_id": run_id})
    return record


@router.post("/runs/{run_id}/checkpoint", response_model=RunResponse)
def decide_run_checkpoint(
    run_id: str,
    body: CheckpointDecisionRequest,
    store: FileStore = Depends(get_store),
) -> RunResponse:
    require_resource_id(run_id)
    record = store.get_run(run_id)
    csv_before = store.dataset_csv_path(record.dataset_id).read_bytes()
    try:
        decision = apply_human_checkpoint(
            _checkpoint_domain(record.human_checkpoint),
            action=body.action,
            run_id=run_id,
            retry_number=record.retry_number,
            note=body.note,
        )
    except CheckpointDecisionError as exc:
        raise ApiError(409, exc.code, exc.message) from exc
    record.status = decision.run_status
    record.accepted = decision.accepted
    record.review_required = decision.review_required
    record.human_checkpoint = _checkpoint_view(decision.checkpoint)
    if decision.run_status == "completed":
        record.finished_at = utc_now()
    traj_path = store.trajectory_path(run_id)
    persist_trajectory_step(traj_path, decision.trajectory_step)
    if decision.continuation_step is not None:
        persist_trajectory_step(traj_path, decision.continuation_step)
    record.trajectory_available = True
    csv_after = store.dataset_csv_path(record.dataset_id).read_bytes()
    if csv_before != csv_after:
        raise ApiError(
            500,
            "source_data_modified",
            "Checkpoint handling must not modify source data.",
        )
    store.put_run(record)
    logger.info(
        "run_checkpoint_decided",
        extra={
            "event": "run_checkpoint_decided",
            "run_id": run_id,
            "action": body.action,
            "checkpoint_status": decision.checkpoint.status,
        },
    )
    return record


def _parse_trajectory_line(raw: str, run_id: str) -> TrajectoryStepView | None:
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        logger.warning(
            "trajectory_line_invalid",
            extra={"event": "trajectory_line_invalid", "run_id": run_id},
        )
        return None
    if not isinstance(payload, dict):
        return None
    timestamp = payload.get("timestamp")
    if isinstance(timestamp, str):
        ts = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    elif isinstance(timestamp, datetime):
        ts = timestamp
    else:
        return None
    try:
        return TrajectoryStepView(
            run_id=str(payload.get("run_id", run_id)),
            agent_id=str(payload.get("agent_id", "")),
            timestamp=ts,
            step_index=int(payload.get("step_index", 0)),
            agent_instruction=str(payload.get("agent_instruction", "")),
            input_state_hash=str(payload.get("input_state_hash", "")),
            input_summary=dict(payload.get("input_summary") or {}),
            tool_invocation=payload.get("tool_invocation"),
            tool_output_ref=payload.get("tool_output_ref"),
            decision=payload.get("decision"),
            evidence_ids=list(payload.get("evidence_ids") or []),
            retry_number=int(payload.get("retry_number", 0)),
            status=str(payload.get("status", payload.get("final_status", ""))),
            next_step=payload.get("next_step"),
            error=payload.get("error"),
            final_result=payload.get("final_result"),
            event_id=payload.get("event_id") if isinstance(payload.get("event_id"), str) else None,
            event_type=(
                payload.get("event_type") if isinstance(payload.get("event_type"), str) else None
            ),
            actor=payload.get("actor") if isinstance(payload.get("actor"), str) else None,
            case_id=payload.get("case_id") if isinstance(payload.get("case_id"), str) else None,
            sequence=payload.get("sequence") if isinstance(payload.get("sequence"), int) else None,
            payload=payload.get("payload") if isinstance(payload.get("payload"), dict) else None,
        )
    except (TypeError, ValueError):
        logger.warning(
            "trajectory_line_invalid",
            extra={"event": "trajectory_line_invalid", "run_id": run_id},
        )
        return None


@router.get("/runs/{run_id}/trajectory", response_model=TrajectoryResponse)
def get_run_trajectory(run_id: str, store: FileStore = Depends(get_store)) -> TrajectoryResponse:
    require_resource_id(run_id)
    store.get_run(run_id)
    path = store.trajectory_path(run_id)
    steps: list[TrajectoryStepView] = []
    if path.is_file():
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            parsed = _parse_trajectory_line(line, run_id)
            if parsed is not None:
                steps.append(parsed)
    logger.info(
        "run_trajectory_fetched",
        extra={"event": "run_trajectory_fetched", "run_id": run_id, "n_steps": len(steps)},
    )
    return TrajectoryResponse(run_id=run_id, steps=steps)
