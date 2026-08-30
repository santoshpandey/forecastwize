from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

import pytest
from app.agents.orchestrator import HumanCheckpoint, OrchestratorState
from app.api.ids import sanitize_upload_filename
from app.config import get_settings
from app.evidence.trajectory import TrajectoryRecord
from app.forecasting.base import ForecastResult
from app.main import create_app
from app.services.forecast_service import run_baseline_forecast
from evaluation.report import AggregateMetrics, BaselineEvaluationResult
from fastapi.testclient import TestClient

from tests.ts_fixtures import daily_index, trend_seasonal

pytestmark = pytest.mark.api

DAILY_CSV = "timestamp,value\n" + "".join(
    f"2020-01-{day:02d},{float(day)}\n" for day in range(1, 15)
)


@pytest.fixture(autouse=True)
def _reset_inflight_jobs() -> Iterator[None]:
    from app.api.job_limit import reset_background_jobs_for_tests

    reset_background_jobs_for_tests()
    yield
    reset_background_jobs_for_tests()


@pytest.fixture
def api_client(tmp_path: Path) -> Iterator[TestClient]:
    application = create_app(store_dir=tmp_path)
    with TestClient(application) as client:
        yield client


def _create_dataset(client: TestClient, csv_text: str = DAILY_CSV) -> str:
    response = client.post(
        "/datasets",
        json={"filename": "series.csv", "csv_text": csv_text},
    )
    assert response.status_code == 201, response.text
    return str(response.json()["id"])


def _stub_forecast() -> ForecastResult:
    stamps = daily_index(14)
    values = trend_seasonal(14)
    return run_baseline_forecast(
        stamps,
        values,
        frequency="D",
        horizon=3,
        model_id="naive",
        generated_at=datetime(2021, 1, 1, tzinfo=UTC),
    )


def _stub_orchestrator(timestamps, values, **kwargs):  # type: ignore[no-untyped-def]
    run_id = str(kwargs["run_id"])
    path = kwargs["trajectory_path"]
    forecast = _stub_forecast()
    if path is not None:
        record = TrajectoryRecord(
            run_id=run_id,
            agent_id="orchestrator",
            timestamp=datetime(2021, 1, 1, tzinfo=UTC),
            step_index=0,
            agent_instruction="Run PROFILE through FINALIZE.",
            input_state_hash="0" * 64,
            input_summary={"n_observations": 14, "frequency": "D", "horizon": 3},
            evidence_ids=["E1"],
            retry_number=0,
            status="completed",
            input_state={"n_observations": 14},
            final_status="completed",
            final_result={"status": "completed"},
        )
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(record.model_dump_json() + "\n", encoding="utf-8")
    return OrchestratorState(
        run_id=run_id,
        status="completed",
        node="FINALIZE",
        nodes_visited=["START", "FINALIZE"],
        frequency="D",
        horizon=3,
        selected_strategy_id="naive",
        verification_ran=True,
        verification_overall="WARN",
        accepted=True,
        forecast=forecast,
        human_checkpoint=HumanCheckpoint(
            required=False,
            status="not_required",
            reason="Verification did not require a checkpoint.",
        ),
    )


def _stub_waiting_orchestrator(timestamps, values, **kwargs):  # type: ignore[no-untyped-def]
    run_id = str(kwargs["run_id"])
    path = kwargs["trajectory_path"]
    forecast = _stub_forecast()
    if path is not None:
        record = TrajectoryRecord(
            run_id=run_id,
            agent_id="orchestrator",
            timestamp=datetime(2021, 1, 1, tzinfo=UTC),
            step_index=0,
            agent_instruction="Run PROFILE through FINALIZE.",
            input_state_hash="0" * 64,
            input_summary={"n_observations": 14, "frequency": "D", "horizon": 3},
            evidence_ids=["E1"],
            retry_number=2,
            status="waiting_for_approval",
            input_state={"n_observations": 14},
            final_status="waiting_for_approval",
            final_result={"status": "waiting_for_approval"},
        )
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(record.model_dump_json() + "\n", encoding="utf-8")
    return OrchestratorState(
        run_id=run_id,
        status="waiting_for_approval",
        node="FINALIZE",
        nodes_visited=["START", "FINALIZE"],
        frequency="D",
        horizon=3,
        selected_strategy_id="naive",
        verification_ran=True,
        verification_overall="FAIL",
        accepted=False,
        review_required=True,
        retry_number=2,
        forecast=forecast,
        human_checkpoint=HumanCheckpoint(
            required=True,
            status="waiting_for_approval",
            reason="Verification FAIL and retries are exhausted.",
            evidence_ids=["E1"],
            triggers=["verification_failed_repeatedly"],
            source_data_unmodified=True,
            checkpoint_id=f"ckpt-{run_id}",
        ),
    )


def _stub_evaluation(system, output_json, output_md):  # type: ignore[no-untyped-def]
    result = BaselineEvaluationResult(
        evaluation_run_id=f"{system}-api-stub",
        timestamp=datetime(2021, 1, 1, tzinfo=UTC),
        git_commit=None,
        system=system,
        catalog_id="fw-eval",
        catalog_version=1,
        case_list=["001"],
        configuration={"source": "api-test-stub"},
        model_configuration={"source": "api-test-stub"},
        per_case=[],
        aggregate=AggregateMetrics(
            n_cases=1,
            n_cases_completed=1,
            n_cases_failed=0,
            wis=1.25,
            smape=0.1,
            wmape=0.1,
            mase=1.0,
            mae=1.0,
            rmse=1.0,
            interval_coverage=0.9,
            interval_width=2.0,
            wis_completed_only=1.25,
            smape_completed_only=0.1,
            wmape_completed_only=0.1,
            mase_completed_only=1.0,
            mae_completed_only=1.0,
            rmse_completed_only=1.0,
            interval_coverage_completed_only=0.9,
            interval_width_completed_only=2.0,
            human_intervention_count=0,
        ),
        errors=[],
        runtime={"wall_seconds": 0.01},
    )
    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(result.model_dump_json(), encoding="utf-8")
    output_md.write_text("# stub\n", encoding="utf-8")
    return result


def test_request_id_is_echoed_and_generated(api_client: TestClient) -> None:
    generated = api_client.get("/health")
    assert generated.status_code == 200
    assert generated.headers.get("X-Request-ID")
    custom = api_client.get("/health", headers={"X-Request-ID": "client-req-1"})
    assert custom.headers["X-Request-ID"] == "client-req-1"


def test_invalid_request_id_is_replaced(api_client: TestClient) -> None:
    response = api_client.get("/health", headers={"X-Request-ID": "not valid id"})
    assert response.headers["X-Request-ID"] != "not valid id"


def test_unknown_route_returns_typed_404(api_client: TestClient) -> None:
    response = api_client.get("/this-route-does-not-exist")
    assert response.status_code == 404
    body = response.json()
    assert body["error_code"] == "not_found"
    assert "request_id" in body
    assert "Traceback" not in body["message"]
    assert "File " not in body["message"]


def test_create_and_get_dataset_json(api_client: TestClient) -> None:
    created = api_client.post(
        "/datasets",
        json={"filename": "sales.csv", "csv_text": DAILY_CSV},
    )
    assert created.status_code == 201
    body = created.json()
    assert body["filename"] == "sales.csv"
    assert body["n_rows"] == 14
    assert body["frequency"] == "D"
    fetched = api_client.get(f"/datasets/{body['id']}")
    assert fetched.status_code == 200
    assert fetched.json()["id"] == body["id"]
    assert len(fetched.json()["points"]) == 14
    assert "anomalies" in fetched.json()
    assert "seasonality" in fetched.json()
    assert "structural_break" in fetched.json()


def test_create_dataset_multipart(api_client: TestClient) -> None:
    response = api_client.post(
        "/datasets",
        files={"file": ("upload.csv", DAILY_CSV.encode("utf-8"), "text/csv")},
    )
    assert response.status_code == 201
    assert response.json()["filename"] == "upload.csv"


def test_dataset_rejects_missing_columns(api_client: TestClient) -> None:
    response = api_client.post(
        "/datasets",
        json={"filename": "bad.csv", "csv_text": "date,amount\n2020-01-01,1\n"},
    )
    assert response.status_code == 422
    body = response.json()
    assert body["error_code"] == "invalid_csv"
    assert "Traceback" not in body["message"]


def test_dataset_rejects_path_traversal_filename() -> None:
    from app.api.errors import ApiError

    with pytest.raises(ApiError):
        sanitize_upload_filename("../secret.csv")


def test_dataset_rejects_traversal_via_api(api_client: TestClient) -> None:
    response = api_client.post(
        "/datasets",
        json={"filename": "../etc/passwd.csv", "csv_text": DAILY_CSV},
    )
    assert response.status_code == 422
    assert response.json()["error_code"] == "invalid_filename"


def test_dataset_rejects_extra_fields(api_client: TestClient) -> None:
    response = api_client.post(
        "/datasets",
        json={"filename": "a.csv", "csv_text": DAILY_CSV, "owner": "secret"},
    )
    assert response.status_code == 422
    assert response.json()["error_code"] == "validation_error"


def test_dataset_oversize_rejected(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MAX_UPLOAD_BYTES", "40")
    get_settings.cache_clear()
    try:
        application = create_app(store_dir=tmp_path)
        with TestClient(application) as client:
            response = client.post(
                "/datasets",
                json={"filename": "a.csv", "csv_text": DAILY_CSV},
            )
        assert response.status_code == 413
        assert response.json()["error_code"] == "payload_too_large"
    finally:
        get_settings.cache_clear()


def test_run_rejected_when_job_cap_hit(
    api_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.api import runs as runs_mod
    from app.api.errors import ApiError

    def deny() -> None:
        raise ApiError(
            429,
            "too_many_jobs",
            "Too many background jobs are already running. Retry later.",
        )

    monkeypatch.setattr(runs_mod, "acquire_background_job", deny)
    dataset_id = _create_dataset(api_client)
    response = api_client.post(
        "/runs",
        json={"dataset_id": dataset_id, "horizon": 3, "frequency": "D", "seed": 1},
    )
    assert response.status_code == 429
    assert response.json()["error_code"] == "too_many_jobs"
    assert "Traceback" not in response.json()["message"]


def test_production_hides_openapi(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_ENV", "production")
    get_settings.cache_clear()
    try:
        application = create_app(store_dir=tmp_path)
        with TestClient(application) as client:
            docs = client.get("/docs")
            spec = client.get("/openapi.json")
        assert docs.status_code == 404
        assert spec.status_code == 404
        assert "Traceback" not in (docs.text + spec.text)
    finally:
        get_settings.cache_clear()


def test_unknown_dataset_is_404(api_client: TestClient) -> None:
    dataset_id = "ds_" + "ab" * 16
    response = api_client.get(f"/datasets/{dataset_id}")
    assert response.status_code == 404
    assert response.json()["error_code"] == "not_found"


def test_malformed_id_is_404_not_path_escape(api_client: TestClient) -> None:
    response = api_client.get("/datasets/not-a-valid-id")
    assert response.status_code == 404
    assert response.json()["error_code"] == "not_found"
    assert "Traceback" not in response.json()["message"]


def test_create_and_get_named_forecast(api_client: TestClient) -> None:
    dataset_id = _create_dataset(api_client)
    created = api_client.post(
        "/forecasts",
        json={
            "dataset_id": dataset_id,
            "model_id": "naive",
            "horizon": 3,
            "frequency": "D",
            "seed": 1,
        },
    )
    assert created.status_code == 201, created.text
    body = created.json()
    assert body["model_id"] == "naive"
    assert body["dataset_id"] == dataset_id
    assert len(body["result"]["yhat"]) == 3
    assert body["result"]["forecast_horizon"] == 3
    fetched = api_client.get(f"/forecasts/{body['id']}")
    assert fetched.status_code == 200
    assert fetched.json()["result"]["yhat"] == body["result"]["yhat"]


def test_forecast_unknown_model_rejected(api_client: TestClient) -> None:
    dataset_id = _create_dataset(api_client)
    response = api_client.post(
        "/forecasts",
        json={"dataset_id": dataset_id, "model_id": "best", "horizon": 3},
    )
    assert response.status_code == 422
    assert response.json()["error_code"] == "validation_error"


def test_forecast_does_not_call_orchestrator(
    api_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    called = {"n": 0}

    def boom(*_args, **_kwargs):  # type: ignore[no-untyped-def]
        called["n"] += 1
        raise AssertionError("orchestrator must not run for POST /forecasts")

    monkeypatch.setattr("app.api.runs.run_orchestrator", boom)
    dataset_id = _create_dataset(api_client)
    response = api_client.post(
        "/forecasts",
        json={"dataset_id": dataset_id, "model_id": "naive", "horizon": 2, "frequency": "D"},
    )
    assert response.status_code == 201
    assert called["n"] == 0


def test_run_is_accepted_then_completes_in_background(
    api_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("app.api.runs.run_orchestrator", _stub_orchestrator)
    dataset_id = _create_dataset(api_client)
    created = api_client.post(
        "/runs",
        json={"dataset_id": dataset_id, "horizon": 3, "frequency": "D", "seed": 1},
    )
    assert created.status_code == 202, created.text
    assert created.json()["status"] == "queued"
    run_id = created.json()["id"]
    fetched = api_client.get(f"/runs/{run_id}")
    assert fetched.status_code == 200
    body = fetched.json()
    assert body["status"] == "completed"
    assert body["selected_strategy_id"] == "naive"
    assert body["forecast"] is not None
    assert len(body["forecast"]["yhat"]) == 3
    traj = api_client.get(f"/runs/{run_id}/trajectory")
    assert traj.status_code == 200
    steps = traj.json()["steps"]
    assert len(steps) == 1
    assert steps[0]["run_id"] == run_id
    assert steps[0]["agent_id"] == "orchestrator"
    assert "Traceback" not in str(steps[0].get("error"))


def test_checkpoint_accept_and_reject_paths(
    api_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("app.api.runs.run_orchestrator", _stub_waiting_orchestrator)
    dataset_id = _create_dataset(api_client)
    csv_before = api_client.get(f"/datasets/{dataset_id}").json()["n_rows"]
    created = api_client.post(
        "/runs",
        json={"dataset_id": dataset_id, "horizon": 3, "frequency": "D", "seed": 1},
    )
    assert created.status_code == 202
    run_id = created.json()["id"]
    waiting = api_client.get(f"/runs/{run_id}")
    assert waiting.json()["status"] == "waiting_for_approval"
    assert waiting.json()["human_checkpoint"]["required"] is True

    accepted = api_client.post(
        f"/runs/{run_id}/checkpoint",
        json={"action": "accept", "note": "ok"},
    )
    assert accepted.status_code == 200, accepted.text
    body = accepted.json()
    assert body["status"] == "completed"
    assert body["accepted"] is True
    assert body["human_checkpoint"]["status"] == "approved"
    assert body["human_checkpoint"]["source_data_unmodified"] is True
    assert body["human_checkpoint"]["checkpoint_id"] == f"ckpt-{run_id}"
    after_accept = api_client.get(f"/datasets/{dataset_id}")
    assert after_accept.json()["n_rows"] == csv_before
    traj = api_client.get(f"/runs/{run_id}/trajectory").json()["steps"]
    human = [step for step in traj if step["agent_id"] == "human"]
    assert human
    assert human[-1]["decision"]["action"] == "accept"
    assert human[-1]["decision"]["transforms_applied"] is False
    assert human[-1]["event_type"] == "HUMAN_DECISION"
    assert human[-1]["payload"]["checkpoint_id"] == f"ckpt-{run_id}"
    assert human[-1]["payload"]["decision"] == "accept"
    completed = [step for step in traj if step.get("event_type") == "RUN_COMPLETED"]
    assert completed
    assert completed[-1]["payload"]["continuation_of"] == "HUMAN_DECISION"
    assert completed[-1]["payload"]["checkpoint_id"] == f"ckpt-{run_id}"

    blocked = api_client.post(f"/runs/{run_id}/checkpoint", json={"action": "reject"})
    assert blocked.status_code == 409
    assert blocked.json()["error_code"] == "checkpoint_not_waiting"

    created_reject = api_client.post(
        "/runs",
        json={"dataset_id": dataset_id, "horizon": 3, "frequency": "D", "seed": 1},
    )
    reject_id = created_reject.json()["id"]
    waiting_reject = api_client.get(f"/runs/{reject_id}")
    finished_before_review = waiting_reject.json()["finished_at"]
    reviewed = api_client.post(
        f"/runs/{reject_id}/checkpoint",
        json={"action": "review", "note": "Need another look."},
    )
    assert reviewed.status_code == 200
    assert reviewed.json()["status"] == "waiting_for_approval"
    assert reviewed.json()["finished_at"] == finished_before_review
    assert reviewed.json()["human_checkpoint"]["status"] == "waiting_for_approval"
    rejected = api_client.post(
        f"/runs/{reject_id}/checkpoint",
        json={"action": "reject", "note": "Do not use this forecast."},
    )
    assert rejected.status_code == 200, rejected.text
    reject_body = rejected.json()
    assert reject_body["accepted"] is False
    assert reject_body["human_checkpoint"]["status"] == "rejected"
    reject_traj = api_client.get(f"/runs/{reject_id}/trajectory").json()["steps"]
    decisions = [
        step["decision"]["action"]
        for step in reject_traj
        if step.get("decision") and step["decision"].get("action") in {"review", "reject"}
    ]
    assert "review" in decisions
    assert "reject" in decisions
    assert reject_traj[-1]["decision"]["action"] == "reject"


def test_checkpoint_rejected_on_completed_run(
    api_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("app.api.runs.run_orchestrator", _stub_orchestrator)
    dataset_id = _create_dataset(api_client)
    created = api_client.post(
        "/runs",
        json={"dataset_id": dataset_id, "horizon": 3, "frequency": "D", "seed": 1},
    )
    run_id = created.json()["id"]
    response = api_client.post(f"/runs/{run_id}/checkpoint", json={"action": "accept"})
    assert response.status_code == 409
    assert response.json()["error_code"] == "checkpoint_not_required"


def test_evaluation_runs_in_background(
    api_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("app.api.evaluations.run_evaluation_job", _stub_evaluation)
    created = api_client.post("/evaluations/run", json={"system": "baseline"})
    assert created.status_code == 202, created.text
    assert created.json()["status"] == "queued"
    evaluation_id = created.json()["id"]
    fetched = api_client.get(f"/evaluations/{evaluation_id}")
    assert fetched.status_code == 200
    body = fetched.json()
    assert body["status"] == "completed"
    assert body["system"] == "baseline"
    assert body["evaluation_run_id"] == "baseline-api-stub"
    assert body["aggregate"]["n_cases"] == 1
    assert body["aggregate"]["wis"] == 1.25


def test_compare_evaluations_uses_backend_relative_improvement(
    api_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("app.api.evaluations.run_evaluation_job", _stub_evaluation)
    baseline = api_client.post("/evaluations/run", json={"system": "baseline"})
    agent = api_client.post("/evaluations/run", json={"system": "agent"})
    assert baseline.status_code == 202
    assert agent.status_code == 202
    compared = api_client.post(
        "/evaluations/compare",
        json={"baseline_id": baseline.json()["id"], "agent_id": agent.json()["id"]},
    )
    assert compared.status_code == 200, compared.text
    body = compared.json()
    assert body["primary_metric"] == "wis"
    assert body["case_lists_identical"] is True
    wis = body["aggregate"]["wis"]
    assert wis["baseline"] == 1.25
    assert wis["agent"] == 1.25
    assert wis["relative_improvement"] == 0.0


def test_compare_rejects_two_baseline_evaluations(
    api_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("app.api.evaluations.run_evaluation_job", _stub_evaluation)
    first = api_client.post("/evaluations/run", json={"system": "baseline"})
    second = api_client.post("/evaluations/run", json={"system": "baseline"})
    compared = api_client.post(
        "/evaluations/compare",
        json={"baseline_id": first.json()["id"], "agent_id": second.json()["id"]},
    )
    assert compared.status_code == 422
    assert compared.json()["error_code"] == "evaluation_system_mismatch"


def test_evaluation_dashboard_serves_committed_comparison_json(
    api_client: TestClient,
) -> None:
    from evaluation.compare import DEFAULT_OUTPUT, ComparisonResult

    expected = ComparisonResult.model_validate_json(DEFAULT_OUTPUT.read_text(encoding="utf-8"))
    response = api_client.get("/evaluations/dashboard")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["artifact_path"] == "evaluation/results/comparison.json"
    comparison = body["comparison"]
    assert comparison["comparison_id"] == expected.comparison_id
    assert comparison["case_list"] == expected.case_list
    assert len(comparison["per_case"]) == len(expected.per_case)
    file_wis = expected.per_case[2].metrics["wis"].relative_improvement
    api_wis = comparison["per_case"][2]["metrics"]["wis"]["relative_improvement"]
    assert api_wis == file_wis
    assert (
        comparison["aggregate"]["metrics"]["wis"]["relative_improvement"]
        == expected.aggregate.metrics["wis"].relative_improvement
    )
    catalog = {row["case_id"]: row for row in body["catalog"]}
    assert catalog["012"]["challenging"] is True


def test_evaluation_changelog_serves_docs_file(api_client: TestClient) -> None:
    response = api_client.get("/evaluations/changelog")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["path"] == "docs/changelog.md"
    assert "EXP-001" in body["markdown"]


def test_production_500_has_no_traceback(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_ENV", "production")
    get_settings.cache_clear()
    try:
        application = create_app(store_dir=tmp_path)
        dataset_id = "ds_" + "cd" * 16

        def boom(*_args, **_kwargs):  # type: ignore[no-untyped-def]
            raise RuntimeError("secret internals\nTraceback (most recent call last)")

        monkeypatch.setattr(application.state.store, "get_dataset", boom)
        with TestClient(application, raise_server_exceptions=False) as client:
            response = client.get(f"/datasets/{dataset_id}")
        assert response.status_code == 500
        body = response.json()
        assert body["error_code"] == "internal_error"
        assert body["message"] == "An unexpected error occurred."
        assert "Traceback" not in body["message"]
        assert "secret internals" not in body["message"]
    finally:
        get_settings.cache_clear()


def test_sanitize_rejects_non_csv() -> None:
    from app.api.errors import ApiError

    with pytest.raises(ApiError):
        sanitize_upload_filename("notes.txt")


def test_candidate_row_view_accepts_exp010_fields() -> None:
    from app.api.schemas import CandidateRowView
    from app.tools.forecasting_tools import CandidateEvalRow

    row = CandidateEvalRow(
        model_id="naive",
        official_wis=1.0,
        wis_completed_only=1.0,
        n_folds_planned=5,
        n_folds_completed=5,
        n_folds_failed=0,
        rank=1,
        min_train_size=14,
        eligible=True,
        selectable=True,
        vetoed=False,
    )
    view = CandidateRowView.model_validate(row.model_dump())
    assert view.model_id == "naive"
    assert view.eligible is True
    assert view.selectable is True
