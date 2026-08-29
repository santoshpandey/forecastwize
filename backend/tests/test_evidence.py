from __future__ import annotations

import inspect
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from app.agents.data_detective import run_data_detective
from app.agents.state import TrajectoryStep
from app.evidence.artifacts import ArtifactRef, ArtifactStore, sanitize_id
from app.evidence.logger import (
    EvidenceLogger,
    hash_canonical,
    load_trajectory,
    persist_trajectory_step,
    redact_object,
    summarize_input,
)
from app.evidence.trajectory import (
    REQUIRED_TRAJECTORY_FIELDS,
    REVIEWER_SEQUENCE,
    TrajectoryRecord,
    reviewer_walk,
)
from pydantic import ValidationError

from tests.ts_fixtures import daily_index, trend_seasonal

_FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures" / "trajectories"
_CREATED = datetime(2021, 3, 1, tzinfo=UTC)


def _step(**kwargs: object) -> TrajectoryStep:
    payload = {
        "run_id": "fixture-run",
        "agent_id": "data_detective",
        "timestamp": _CREATED,
        "input_state": {"n_observations": 36, "frequency": "D", "agent_id": "data_detective"},
        "tool_requested": None,
        "tool_result": None,
        "decision": None,
        "evidence_ids": ["E1"],
        "retry_number": 0,
        "final_status": "running",
    }
    payload.update(kwargs)
    return TrajectoryStep(**payload)  # type: ignore[arg-type]


def test_evidence_source_has_no_fastapi_or_llm() -> None:
    from app.evidence import artifacts, logger, trajectory

    for module in (artifacts, logger, trajectory):
        text = inspect.getsource(module).lower()
        assert "import fastapi" not in text
        assert "import openai" not in text
        assert "langgraph" not in text
        assert "yhat =" not in text


def test_hash_is_stable_and_ignores_key_order() -> None:
    left = {"frequency": "D", "n_observations": 36}
    right = {"n_observations": 36, "frequency": "D"}
    assert hash_canonical(left) == hash_canonical(right)
    assert len(hash_canonical(left)) == 64


def test_redact_secrets_and_omit_raw_series() -> None:
    payload = {
        "api_key": "sk-secretvalue123456",
        "OPENAI_API_KEY": "sk-other",
        "values": [1.0, 2.0, 3.0],
        "n_observations": 3,
        "note": "password=hunter2 in prose",
    }
    cleaned = summarize_input(payload)
    dumped = json.dumps(cleaned)
    assert "sk-secretvalue123456" not in dumped
    assert "hunter2" not in dumped
    assert cleaned["api_key"] == "[redacted]"
    assert cleaned["values"]["omitted"] is True
    assert cleaned["values"]["n"] == 3
    assert cleaned["n_observations"] == 3
    assert "[redacted]" in json.dumps(redact_object(payload))


def test_append_only_jsonl_and_artifact_ref(tmp_path: Path) -> None:
    path = tmp_path / "run.jsonl"
    logger = EvidenceLogger(path, artifact_store=ArtifactStore(tmp_path / "artifacts"))
    first = logger.log_step(
        _step(
            run_id="run-one",
            tool_requested="inspect_series",
            tool_result={"ok": True, "payload": {"n_rows": 36, "values": [0.0, 1.0]}},
            decision={"next": "DIAGNOSE"},
        )
    )
    second = logger.log_step(
        _step(
            run_id="run-one",
            tool_requested=None,
            decision={"status": "completed"},
            final_status="completed",
            evidence_ids=["E1", "E2"],
        )
    )
    lines = path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    assert first.step_index == 0
    assert second.step_index == 1
    loaded = load_trajectory(path)
    assert [row.step_index for row in loaded] == [0, 1]
    for row in loaded:
        for field in REQUIRED_TRAJECTORY_FIELDS:
            assert field in row.model_dump()
    assert first.tool_output_ref is not None
    artifact = ArtifactRef(
        artifact_id=first.tool_output_ref.artifact_id,
        sha256=first.tool_output_ref.sha256,
        kind="tool_output",
        relative_path=f"run-one/{first.tool_output_ref.artifact_id}.json",
        byte_length=1,
    )
    stored = ArtifactStore(tmp_path / "artifacts").read_json(artifact)
    dumped = json.dumps(stored)
    assert "0.0" not in dumped
    assert stored["payload"]["values"]["omitted"] is True
    assert first.input_state_hash == hash_canonical(first.input_summary)
    assert second.final_result is not None
    assert second.final_result["status"] == "completed"
    walk = reviewer_walk(loaded)
    assert list(walk[0].keys()) == list(REVIEWER_SEQUENCE)
    assert "Inspect diagnostics" in walk[0]["agent_instruction"]
    assert walk[0]["next_step"] == "DIAGNOSE"
    assert walk[1]["tool_invocation"] is None
    assert walk[1]["final_result"]["status"] == "completed"
    assert "sk-" not in path.read_text(encoding="utf-8")


def test_failed_step_records_error(tmp_path: Path) -> None:
    path = tmp_path / "fail.jsonl"
    persist_trajectory_step(
        path,
        _step(
            run_id="run-fail",
            tool_requested="inspect_series",
            tool_result={
                "ok": False,
                "error_type": "InvalidInput",
                "error_message": "bad csv api_key=sk-leak1234567890",
            },
            final_status="failed",
        ),
    )
    record = load_trajectory(path)[0]
    assert record.status == "failed"
    assert record.error is not None
    assert record.error.error_type == "InvalidInput"
    assert "sk-leak" not in record.error.error_message
    assert record.final_result is not None
    text = path.read_text(encoding="utf-8")
    assert "sk-leak1234567890" not in text
    artifact_dir = path.parent / "artifacts" / "run-fail"
    artifact_text = next(artifact_dir.glob("*.json")).read_text(encoding="utf-8")
    assert "sk-leak1234567890" not in artifact_text


def test_sanitize_rejects_path_traversal() -> None:
    with pytest.raises(ValueError, match="invalid run_id"):
        sanitize_id("../secrets", label="run_id")
    with pytest.raises(ValueError, match="invalid artifact_id"):
        sanitize_id("a/b", label="artifact_id")


def test_failed_record_without_error_is_rejected() -> None:
    with pytest.raises(ValidationError, match="error information"):
        TrajectoryRecord(
            run_id="x",
            agent_id="data_detective",
            timestamp=_CREATED,
            step_index=0,
            agent_instruction="Inspect diagnostics only.",
            input_state_hash="a" * 64,
            input_summary={"n_observations": 1},
            evidence_ids=["E1"],
            retry_number=0,
            status="failed",
            input_state={"n_observations": 1},
            final_status="failed",
        )


def test_fixtures_are_reviewable_json() -> None:
    names = (
        "successful_run.jsonl",
        "verification_retry.jsonl",
        "tool_failure.jsonl",
    )
    for name in names:
        path = _FIXTURE_DIR / name
        records = load_trajectory(path)
        assert records
        walk = reviewer_walk(records)
        assert len(walk) == len(records)
        for record, frame in zip(records, walk, strict=True):
            dumped = record.model_dump(mode="json")
            for field in REQUIRED_TRAJECTORY_FIELDS:
                assert field in dumped
            assert list(frame.keys()) == list(REVIEWER_SEQUENCE)
            assert record.agent_instruction
            assert record.input_state_hash
        text = path.read_text(encoding="utf-8")
        assert "sk-" not in text
        assert '"values": [1' not in text


def test_live_agent_jsonl_uses_canonical_fields(tmp_path: Path) -> None:
    n = 36
    state = run_data_detective(
        daily_index(n),
        trend_seasonal(n),
        frequency="D",
        run_id="evidence-live",
        generated_at=_CREATED,
        trajectory_path=tmp_path / "live.jsonl",
    )
    assert state.status == "completed"
    records = load_trajectory(tmp_path / "live.jsonl")
    assert records
    assert records[-1].status == "completed"
    assert records[-1].final_result is not None
    assert any(row.tool_requested == "inspect_series" for row in records)
    assert any(row.tool_output_ref is not None for row in records)
    blob = (tmp_path / "live.jsonl").read_text(encoding="utf-8")
    assert "input_state_hash" in blob
    assert "agent_instruction" in blob
    assert "sk-" not in blob
    for record in records:
        assert record.input_state_hash == hash_canonical(record.input_summary)
