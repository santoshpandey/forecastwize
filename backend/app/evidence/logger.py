"""Append-only evidence/trajectory logger. No FastAPI. No LLM. No secrets in files."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any

from app.agents.state import TrajectoryStep
from app.evidence.artifacts import ArtifactRef, ArtifactStore
from app.evidence.trajectory import (
    ToolInvocation,
    ToolOutputRef,
    TrajectoryError,
    TrajectoryRecord,
    TrajectoryStatus,
    instruction_for,
)

JsonObject = dict[str, Any]

_SECRET_KEY_FRAGMENTS = ("key", "secret", "token", "password", "authorization")
_SERIES_KEYS = frozenset(
    {
        "values",
        "train_values",
        "raw_values",
        "series",
        "actuals",
        "residuals",
        "timestamps",
    }
)
_SECRET_IN_TEXT = re.compile(r"(?i)(api[_-]?key|token|password|secret|authorization)\s*[:=]\s*\S+")
_SK_PATTERN = re.compile(r"sk-[A-Za-z0-9]{10,}")


def canonical_json(payload: Any) -> str:
    return json.dumps(
        payload, sort_keys=True, separators=(",", ":"), default=str, ensure_ascii=True
    )


def hash_canonical(payload: Any) -> str:
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


def redact_text(value: str) -> str:
    out = _SECRET_IN_TEXT.sub(lambda match: f"{match.group(1)}=[redacted]", value)
    return _SK_PATTERN.sub("[redacted]", out)


def redact_object(payload: Any, *, key: str = "") -> Any:
    if key and any(fragment in key.lower() for fragment in _SECRET_KEY_FRAGMENTS):
        return "[redacted]"
    if isinstance(payload, dict):
        return {
            str(item_key): redact_object(value, key=str(item_key))
            for item_key, value in payload.items()
        }
    if isinstance(payload, list):
        return [redact_object(item, key=key) for item in payload]
    if isinstance(payload, str):
        return redact_text(payload)
    return payload


def strip_raw_series(payload: Any) -> Any:
    """Drop training-series dumps from summaries. Forecast yhat in tool payloads is kept."""
    if isinstance(payload, dict):
        out: JsonObject = {}
        for item_key, value in payload.items():
            if item_key in _SERIES_KEYS:
                omitted: JsonObject = {"omitted": True, "reason": "raw_series_not_stored"}
                if hasattr(value, "__len__") and not isinstance(value, str | dict):
                    omitted["n"] = len(value)
                out[item_key] = omitted
                continue
            out[item_key] = strip_raw_series(value)
        return out
    if isinstance(payload, list):
        return [strip_raw_series(item) for item in payload]
    return payload


def summarize_input(payload: JsonObject) -> JsonObject:
    return strip_raw_series(redact_object(payload))


class EvidenceLogger:
    """Writes one JSON object per line. Never rewrites prior lines."""

    def __init__(
        self, trajectory_path: Path, *, artifact_store: ArtifactStore | None = None
    ) -> None:
        self.path = trajectory_path
        self.artifact_store = artifact_store
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def next_step_index(self) -> int:
        if not self.path.exists():
            return 0
        return sum(1 for line in self.path.read_text(encoding="utf-8").splitlines() if line.strip())

    def append(self, record: TrajectoryRecord) -> None:
        line = record.model_dump_json()
        with self.path.open("a", encoding="utf-8", newline="\n") as handle:
            handle.write(line + "\n")

    def log_step(self, step: TrajectoryStep) -> TrajectoryRecord:
        record = build_record(
            step,
            step_index=self.next_step_index(),
            artifact_store=self.artifact_store,
        )
        self.append(record)
        return record


def persist_trajectory_step(path: Path | None, step: TrajectoryStep) -> TrajectoryRecord:
    """Shared persist used by every agent. `path is None` skips disk writes."""
    store = None
    if path is not None:
        store = ArtifactStore(path.parent / "artifacts")
        logger = EvidenceLogger(path, artifact_store=store)
        return logger.log_step(step)
    return build_record(step, step_index=0, artifact_store=None)


def load_trajectory(path: Path) -> list[TrajectoryRecord]:
    records: list[TrajectoryRecord] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        records.append(TrajectoryRecord.model_validate_json(line))
    return records


def build_record(
    step: TrajectoryStep,
    *,
    step_index: int,
    artifact_store: ArtifactStore | None,
) -> TrajectoryRecord:
    snapshot = summarize_input(dict(step.input_state))
    digest = hash_canonical(snapshot)
    node = snapshot.get("node") if isinstance(snapshot.get("node"), str) else None
    instruction = instruction_for(step.agent_id, node=node)
    tool_name = step.tool_requested
    invocation = None
    if tool_name is not None:
        invocation = ToolInvocation(tool_name=tool_name, arguments_summary=_args_summary(snapshot))
    compact_result, output_ref = _persist_tool_output(
        run_id=step.run_id,
        step_index=step_index,
        tool_result=step.tool_result,
        artifact_store=artifact_store,
    )
    error = _error_from(step.tool_result, step.final_status)
    next_step = _next_step(step.decision, step.final_status)
    final_result = _final_result(step.final_status, step.decision, error, step.evidence_ids)
    status: TrajectoryStatus = step.final_status
    return TrajectoryRecord(
        run_id=step.run_id,
        agent_id=step.agent_id,
        timestamp=step.timestamp,
        step_index=step_index,
        agent_instruction=instruction,
        input_state_hash=digest,
        input_summary=snapshot,
        tool_invocation=invocation,
        tool_output_ref=output_ref,
        decision=redact_object(step.decision) if step.decision is not None else None,
        evidence_ids=list(step.evidence_ids),
        retry_number=step.retry_number,
        status=status,
        next_step=next_step,
        error=error,
        final_result=final_result,
        input_state=snapshot,
        tool_requested=tool_name,
        tool_result=compact_result,
        final_status=status,
    )


def _persist_tool_output(
    *,
    run_id: str,
    step_index: int,
    tool_result: JsonObject | None,
    artifact_store: ArtifactStore | None,
) -> tuple[JsonObject | None, ToolOutputRef | None]:
    if tool_result is None:
        return None, None
    cleaned = strip_raw_series(redact_object(tool_result))
    compact: JsonObject = {
        "ok": cleaned.get("ok") if isinstance(cleaned, dict) else None,
        "error_type": cleaned.get("error_type") if isinstance(cleaned, dict) else None,
    }
    if not isinstance(cleaned, dict):
        return {"summary": "non-object tool result omitted"}, None
    if artifact_store is None:
        compact["payload_omitted"] = True
        return compact, None
    body = canonical_json(cleaned)
    digest = hash_canonical(cleaned)
    artifact_id = f"A{step_index}-{digest[:8]}"
    ref: ArtifactRef = artifact_store.write_json(
        run_id=run_id,
        artifact_id=artifact_id,
        body=body,
        sha256=digest,
        kind="tool_output",
    )
    compact["artifact_id"] = ref.artifact_id
    compact["sha256"] = ref.sha256
    output = ToolOutputRef(
        artifact_id=ref.artifact_id,
        sha256=ref.sha256,
        kind=ref.kind,
        ok=compact["ok"] if isinstance(compact["ok"], bool) else None,
    )
    return compact, output


def _error_from(tool_result: JsonObject | None, status: TrajectoryStatus) -> TrajectoryError | None:
    if isinstance(tool_result, dict):
        error_type = tool_result.get("error_type")
        error_message = tool_result.get("error_message")
        if isinstance(error_type, str) and error_type:
            message = error_message if isinstance(error_message, str) else error_type
            return TrajectoryError(error_type=error_type, error_message=redact_text(message))
    if status == "failed":
        return TrajectoryError(error_type="Failed", error_message="step failed")
    return None


def _next_step(decision: JsonObject | None, status: TrajectoryStatus) -> str | None:
    if status in {"completed", "failed", "waiting_for_approval"}:
        return None
    if not isinstance(decision, dict):
        return None
    nxt = decision.get("next")
    if isinstance(nxt, str) and nxt:
        return nxt
    action = decision.get("action")
    if action == "retry":
        return "FORECAST"
    if action == "accept":
        return "ANALYZE"
    if action == "review_required":
        return "ANALYZE"
    if action in {"accept", "reject", "review"}:
        return None
    return None


def _final_result(
    status: TrajectoryStatus,
    decision: JsonObject | None,
    error: TrajectoryError | None,
    evidence_ids: list[str],
) -> JsonObject | None:
    if status not in {"completed", "failed", "waiting_for_approval"}:
        return None
    result: JsonObject = {"status": status, "evidence_ids": list(evidence_ids)}
    if isinstance(decision, dict):
        if "status" in decision:
            result["decision_status"] = decision.get("status")
        if "action" in decision:
            result["action"] = decision.get("action")
        if "review_required" in decision:
            result["review_required"] = decision.get("review_required")
        if decision.get("actor") == "human":
            result["human_action"] = decision.get("action")
            result["checkpoint_status"] = decision.get("checkpoint_status")
            result["source_data_unmodified"] = decision.get("source_data_unmodified")
    if error is not None:
        result["error_type"] = error.error_type
    return result


def _args_summary(snapshot: JsonObject) -> JsonObject:
    keep = (
        "n_observations",
        "frequency",
        "horizon",
        "node",
        "selected_strategy_id",
        "n_train",
        "n_forecast",
        "model",
    )
    return {key: snapshot[key] for key in keep if key in snapshot}
