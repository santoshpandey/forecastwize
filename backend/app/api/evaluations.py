"""Evaluation HTTP adapter. Runs the shared harness in the background; no score invention."""

from __future__ import annotations

import logging
import sys
from datetime import UTC, datetime
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, Depends, Request

from app.api.deps import get_store
from app.api.errors import ApiError
from app.api.ids import new_prefixed_id, require_resource_id
from app.api.job_limit import acquire_background_job, release_background_job
from app.api.schemas import (
    AggregateComparisonView,
    CaseComparisonView,
    CatalogCaseView,
    ChangelogDocumentResponse,
    ComparisonArtifactView,
    EvaluationAggregateView,
    EvaluationCaseError,
    EvaluationCompareRequest,
    EvaluationCompareResponse,
    EvaluationCreateRequest,
    EvaluationDashboardResponse,
    EvaluationResponse,
    EvaluationSystem,
    MetricComparisonView,
    RunErrorView,
)
from app.api.store import FileStore
from app.request_context import set_request_id
from app.time_utils import utc_now

router = APIRouter(tags=["evaluations"])
logger = logging.getLogger(__name__)

_REPO_ROOT = Path(__file__).resolve().parents[3]


def _ensure_repo_on_path() -> None:
    root = str(_REPO_ROOT)
    if root not in sys.path:
        sys.path.insert(0, root)


def ensure_evaluation_available() -> None:
    """Fail fast if this process cannot import the shared evaluation package."""
    _ensure_repo_on_path()
    try:
        from evaluation.cases.generators.catalog import DATA_DIR, REGISTRY_PATH
    except ImportError as exc:
        raise ApiError(
            503,
            "evaluation_unavailable",
            "The evaluation package is not available in this process.",
        ) from exc
    if not REGISTRY_PATH.is_file() or not DATA_DIR.is_dir():
        raise ApiError(
            503,
            "evaluation_unavailable",
            "The shared evaluation catalog is not available.",
        )


def run_evaluation_job(
    system: EvaluationSystem,
    output_json: Path,
    output_md: Path,
) -> object:
    """Invoke the same harness as the CLI. Writes to caller-supplied paths only."""
    _ensure_repo_on_path()
    if system == "baseline":
        from evaluation.run_baseline import run_baseline_evaluation

        return run_baseline_evaluation(output_json=output_json, output_md=output_md)
    from evaluation.run_agent import run_agent_evaluation

    return run_agent_evaluation(
        output_json=output_json,
        output_md=output_md,
        persist_trajectory=True,
    )


def _aggregate_view(result: object) -> EvaluationAggregateView | None:
    aggregate = getattr(result, "aggregate", None)
    if aggregate is None:
        return None
    return EvaluationAggregateView(
        n_cases=int(aggregate.n_cases),
        n_cases_completed=int(aggregate.n_cases_completed),
        n_cases_failed=int(aggregate.n_cases_failed),
        wis=aggregate.wis,
        smape=aggregate.smape,
        wmape=aggregate.wmape,
        mase=aggregate.mase,
        interval_coverage=aggregate.interval_coverage,
        interval_width=aggregate.interval_width,
        human_intervention_count=int(aggregate.human_intervention_count),
        wis_completed_only=aggregate.wis_completed_only,
    )


def _case_errors(result: object) -> list[EvaluationCaseError]:
    raw = getattr(result, "errors", None) or []
    out: list[EvaluationCaseError] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        case_id = item.get("case_id")
        if not isinstance(case_id, str):
            continue
        error_type = item.get("error_type")
        error_message = item.get("error_message")
        out.append(
            EvaluationCaseError(
                case_id=case_id,
                error_type=error_type if isinstance(error_type, str) else None,
                error_message=error_message if isinstance(error_message, str) else None,
            )
        )
    return out


def execute_evaluation(store: FileStore, evaluation_id: str, request_id: str | None) -> None:
    try:
        set_request_id(request_id)
        record = store.get_evaluation(evaluation_id)
        record.status = "running"
        record.started_at = utc_now()
        store.put_evaluation(record)
        result_dir = store.evaluation_result_dir(evaluation_id)
        result_dir.mkdir(parents=True, exist_ok=True)
        json_path = store.contained_file(result_dir, "result.json")
        md_path = store.contained_file(result_dir, "result.md")
        try:
            result = run_evaluation_job(record.system, json_path, md_path)
            record.status = "completed"
            record.finished_at = utc_now()
            record.evaluation_run_id = str(getattr(result, "evaluation_run_id"))
            case_list = getattr(result, "case_list", None)
            record.case_list = list(case_list) if case_list is not None else None
            record.aggregate = _aggregate_view(result)
            record.errors = _case_errors(result)
            logger.info(
                "evaluation_finished",
                extra={
                    "event": "evaluation_finished",
                    "evaluation_id": evaluation_id,
                    "evaluation_run_id": record.evaluation_run_id,
                    "system": record.system,
                },
            )
        except ApiError as exc:
            record.status = "failed"
            record.finished_at = utc_now()
            record.error = RunErrorView(error_code=exc.error_code, message=exc.message)
            logger.info(
                "evaluation_failed",
                extra={
                    "event": "evaluation_failed",
                    "evaluation_id": evaluation_id,
                    "error_code": exc.error_code,
                },
            )
        except Exception:
            logger.exception(
                "evaluation_failed",
                extra={"event": "evaluation_failed", "evaluation_id": evaluation_id},
            )
            record.status = "failed"
            record.finished_at = utc_now()
            record.error = RunErrorView(
                error_code="internal_error",
                message="The evaluation run failed.",
            )
        store.put_evaluation(record)
    finally:
        release_background_job()
        set_request_id(None)


@router.post("/evaluations/run", response_model=EvaluationResponse, status_code=202)
def create_evaluation(
    body: EvaluationCreateRequest,
    background: BackgroundTasks,
    request: Request,
    store: FileStore = Depends(get_store),
) -> EvaluationResponse:
    ensure_evaluation_available()
    evaluation_id = new_prefixed_id("ev")
    record = EvaluationResponse(
        id=evaluation_id,
        status="queued",
        system=body.system,
        created_at=utc_now(),
    )
    acquire_background_job()
    try:
        store.put_evaluation(record)
    except Exception:
        release_background_job()
        raise
    request_id = getattr(request.state, "request_id", None)
    background.add_task(execute_evaluation, store, evaluation_id, request_id)
    logger.info(
        "evaluation_queued",
        extra={
            "event": "evaluation_queued",
            "evaluation_id": evaluation_id,
            "system": body.system,
        },
    )
    return record


def _load_evaluation_artifact(store: FileStore, evaluation_id: str):
    require_resource_id(evaluation_id)
    record = store.get_evaluation(evaluation_id)
    if record.status != "completed":
        raise ApiError(
            409,
            "evaluation_incomplete",
            f"Evaluation {evaluation_id} is not completed.",
        )
    path = store.contained_file(store.evaluation_result_dir(evaluation_id), "result.json")
    if not path.is_file():
        raise ApiError(409, "evaluation_incomplete", "Evaluation artifact was not found.")
    _ensure_repo_on_path()
    from evaluation.report import BaselineEvaluationResult

    return BaselineEvaluationResult.model_validate_json(path.read_text(encoding="utf-8"))


def _metric_view(item: object) -> MetricComparisonView:
    return MetricComparisonView(
        name=str(getattr(item, "name")),
        direction=str(getattr(item, "direction")),
        baseline=getattr(item, "baseline"),
        agent=getattr(item, "agent"),
        delta_agent_minus_baseline=getattr(item, "delta_agent_minus_baseline"),
        relative_improvement=getattr(item, "relative_improvement"),
    )


def _error_views(raw: object) -> list[EvaluationCaseError]:
    if not isinstance(raw, list):
        return []
    out: list[EvaluationCaseError] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        case_id = item.get("case_id")
        if not isinstance(case_id, str):
            continue
        error_type = item.get("error_type")
        error_message = item.get("error_message")
        out.append(
            EvaluationCaseError(
                case_id=case_id,
                error_type=error_type if isinstance(error_type, str) else None,
                error_message=error_message if isinstance(error_message, str) else None,
            )
        )
    return out


@router.post("/evaluations/compare", response_model=EvaluationCompareResponse)
def compare_evaluations_endpoint(
    body: EvaluationCompareRequest,
    store: FileStore = Depends(get_store),
) -> EvaluationCompareResponse:
    ensure_evaluation_available()
    baseline = store.get_evaluation(body.baseline_id)
    agent = store.get_evaluation(body.agent_id)
    if baseline.system != "baseline" or agent.system != "agent":
        raise ApiError(
            422,
            "evaluation_system_mismatch",
            "Compare requires one baseline evaluation and one agent evaluation.",
        )
    baseline_result = _load_evaluation_artifact(store, body.baseline_id)
    agent_result = _load_evaluation_artifact(store, body.agent_id)
    _ensure_repo_on_path()
    from evaluation.compare import CaseListMismatchError, compare_evaluations

    try:
        result = compare_evaluations(baseline_result, agent_result)
    except CaseListMismatchError as exc:
        raise ApiError(422, "case_list_mismatch", str(exc)) from exc
    errors = {key: _error_views(value) for key, value in result.errors.items()}
    logger.info(
        "evaluation_compared",
        extra={
            "event": "evaluation_compared",
            "comparison_id": result.comparison_id,
            "baseline_id": body.baseline_id,
            "agent_id": body.agent_id,
        },
    )
    return EvaluationCompareResponse(
        comparison_id=result.comparison_id,
        baseline_evaluation_run_id=result.baseline_evaluation_run_id,
        agent_evaluation_run_id=result.agent_evaluation_run_id,
        case_list=list(result.case_list),
        case_lists_identical=result.case_lists_identical,
        primary_metric=result.primary_metric,
        aggregate={name: _metric_view(item) for name, item in result.aggregate.metrics.items()},
        n_cases_failed=_metric_view(result.aggregate.n_cases_failed),
        human_intervention_count=_metric_view(result.aggregate.human_intervention_count),
        notes=list(result.notes),
        errors=errors,
    )


def _comparison_artifact_view(result: object) -> ComparisonArtifactView:
    aggregate = getattr(result, "aggregate")
    return ComparisonArtifactView(
        comparison_id=str(getattr(result, "comparison_id")),
        timestamp=_to_iso(getattr(result, "timestamp")),
        git_commit=getattr(result, "git_commit"),
        baseline_evaluation_run_id=str(getattr(result, "baseline_evaluation_run_id")),
        agent_evaluation_run_id=str(getattr(result, "agent_evaluation_run_id")),
        case_list=list(getattr(result, "case_list")),
        case_lists_identical=bool(getattr(result, "case_lists_identical")),
        primary_metric=str(getattr(result, "primary_metric")),
        per_case=[_case_view(row) for row in getattr(result, "per_case")],
        aggregate=AggregateComparisonView(
            n_cases=int(aggregate.n_cases),
            metrics={name: _metric_view(item) for name, item in aggregate.metrics.items()},
            n_cases_failed=_metric_view(aggregate.n_cases_failed),
            human_intervention_count=_metric_view(aggregate.human_intervention_count),
            wall_seconds=_metric_view(aggregate.wall_seconds),
            cases_seconds=_metric_view(aggregate.cases_seconds),
        ),
        errors={key: _error_views(value) for key, value in getattr(result, "errors").items()},
        notes=list(getattr(result, "notes")),
    )


def _case_view(row: object) -> CaseComparisonView:
    return CaseComparisonView(
        case_id=str(getattr(row, "case_id")),
        baseline_status=str(getattr(row, "baseline_status")),
        agent_status=str(getattr(row, "agent_status")),
        baseline_error_type=getattr(row, "baseline_error_type"),
        agent_error_type=getattr(row, "agent_error_type"),
        baseline_error_message=getattr(row, "baseline_error_message"),
        agent_error_message=getattr(row, "agent_error_message"),
        review_required=bool(getattr(row, "review_required")),
        retry_number=int(getattr(row, "retry_number")),
        metrics={name: _metric_view(item) for name, item in getattr(row, "metrics").items()},
        runtime_seconds=_metric_view(getattr(row, "runtime_seconds")),
    )


def _to_iso(value: object) -> str:
    if isinstance(value, str):
        return value
    if not isinstance(value, datetime):
        return str(value)
    aware = value if value.tzinfo is not None else value.replace(tzinfo=UTC)
    return aware.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _catalog_views() -> list[CatalogCaseView]:
    from evaluation.cases.generators.catalog import load_catalog

    catalog = load_catalog()
    return [
        CatalogCaseView(
            case_id=case.case_id,
            name=case.name,
            expected_challenge=case.expected_challenge,
            description=case.description.strip(),
            challenging="adversarial" in case.expected_challenge,
        )
        for case in catalog.cases
    ]


@router.get("/evaluations/dashboard", response_model=EvaluationDashboardResponse)
def get_evaluation_dashboard() -> EvaluationDashboardResponse:
    """Serve committed evaluation JSON. Does not recompute WIS or improvement."""
    ensure_evaluation_available()
    _ensure_repo_on_path()
    from evaluation.compare import (
        DEFAULT_AGENT,
        DEFAULT_BASELINE,
        DEFAULT_OUTPUT,
        ComparisonResult,
    )

    if not DEFAULT_OUTPUT.is_file():
        raise ApiError(
            404,
            "evaluation_artifact_missing",
            "evaluation/results/comparison.json was not found.",
        )
    result = ComparisonResult.model_validate_json(DEFAULT_OUTPUT.read_text(encoding="utf-8"))
    logger.info(
        "evaluation_dashboard_loaded",
        extra={
            "event": "evaluation_dashboard_loaded",
            "comparison_id": result.comparison_id,
        },
    )
    return EvaluationDashboardResponse(
        artifact_path="evaluation/results/comparison.json",
        baseline_artifact_path=(
            "evaluation/results/baseline.json" if DEFAULT_BASELINE.is_file() else None
        ),
        agent_artifact_path="evaluation/results/agent.json" if DEFAULT_AGENT.is_file() else None,
        changelog_path="docs/changelog.md",
        comparison=_comparison_artifact_view(result),
        catalog=_catalog_views(),
    )


def _changelog_document_path() -> Path:
    docs_dir = (_REPO_ROOT / "docs").resolve()
    path = (docs_dir / "changelog.md").resolve()
    if not path.is_relative_to(docs_dir) or path.name != "changelog.md":
        raise ApiError(500, "storage_error", "Changelog path is not allowed.")
    return path


@router.get("/evaluations/changelog", response_model=ChangelogDocumentResponse)
def get_evaluation_changelog() -> ChangelogDocumentResponse:
    path = _changelog_document_path()
    if not path.is_file():
        raise ApiError(404, "not_found", "docs/changelog.md was not found.")
    return ChangelogDocumentResponse(
        path="docs/changelog.md",
        markdown=path.read_text(encoding="utf-8"),
    )


@router.get("/evaluations/{evaluation_id}", response_model=EvaluationResponse)
def get_evaluation(evaluation_id: str, store: FileStore = Depends(get_store)) -> EvaluationResponse:
    require_resource_id(evaluation_id)
    record = store.get_evaluation(evaluation_id)
    logger.info(
        "evaluation_fetched",
        extra={"event": "evaluation_fetched", "evaluation_id": evaluation_id},
    )
    return record
