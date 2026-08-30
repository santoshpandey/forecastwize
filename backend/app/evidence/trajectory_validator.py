"""Validate persisted evaluation trajectories. Observational; no forecast math."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from app.evidence.logger import load_trajectory
from app.evidence.trajectory import VALID_EVENT_TYPES, TrajectoryRecord

JsonObject = dict[str, Any]

_SECRET_FRAGMENTS = ("sk-", "api_key=", "password=", "authorization=")

_TERMINAL_EVENTS = frozenset({"RUN_COMPLETED", "RUN_FAILED"})

_IMPOSSIBLE_BEFORE_START = frozenset(
    {
        "RUN_COMPLETED",
        "RUN_FAILED",
        "FORECAST_COMPLETED",
        "VERIFICATION_COMPLETED",
        "MODEL_SELECTED",
        "HUMAN_DECISION",
    }
)


class TrajectoryValidationError(ValueError):
    def __init__(self, message: str, *, path: Path | None = None) -> None:
        super().__init__(message)
        self.path = path
        self.message = message


def validate_trajectory_file(
    path: Path,
    *,
    expected_case_id: str | None = None,
    expected_run_id: str | None = None,
    require_terminal_run_event: bool = True,
    require_case_id: bool = True,
) -> list[TrajectoryRecord]:
    """Validate one JSONL case trajectory. Does not invent missing events.

    Catalog files must keep ``require_case_id=True``. Interactive API demos
    may omit case_id; pass ``require_case_id=False`` for those files only.
    """
    if not path.is_file():
        raise TrajectoryValidationError(f"trajectory file missing: {path}", path=path)
    try:
        records = load_trajectory(path)
    except Exception as exc:
        raise TrajectoryValidationError(f"invalid JSONL: {exc}", path=path) from exc
    if not records:
        raise TrajectoryValidationError("trajectory is empty", path=path)
    seen_ids: set[str] = set()
    run_ids: set[str] = set()
    case_ids: set[str] = set()
    last_sequence = -1
    started = False
    for record in records:
        _validate_record(record, path=path, require_case_id=require_case_id)
        if record.event_id is None:
            raise TrajectoryValidationError("event_id is required", path=path)
        if record.event_id in seen_ids:
            raise TrajectoryValidationError(f"duplicate event_id {record.event_id}", path=path)
        seen_ids.add(record.event_id)
        run_ids.add(record.run_id)
        if record.case_id is not None:
            case_ids.add(record.case_id)
        sequence = record.sequence if record.sequence is not None else record.step_index
        if sequence <= last_sequence:
            raise TrajectoryValidationError(
                f"sequence is not monotonically increasing at {record.event_id}",
                path=path,
            )
        last_sequence = sequence
        if record.event_type == "RUN_STARTED":
            started = True
        if record.event_type in _IMPOSSIBLE_BEFORE_START and not started:
            raise TrajectoryValidationError(
                f"{record.event_type} appeared before RUN_STARTED",
                path=path,
            )
        lowered = record.model_dump_json().lower()
        for fragment in _SECRET_FRAGMENTS:
            if fragment in lowered and "[redacted]" not in lowered:
                raise TrajectoryValidationError(
                    f"secret-like value {fragment!r} in trajectory",
                    path=path,
                )
    if len(run_ids) != 1:
        raise TrajectoryValidationError(f"expected one run_id, found {sorted(run_ids)}", path=path)
    only_run = next(iter(run_ids))
    if expected_run_id is not None and only_run != expected_run_id:
        raise TrajectoryValidationError(
            f"run_id {only_run!r} != expected {expected_run_id!r}",
            path=path,
        )
    if expected_case_id is not None:
        if not case_ids:
            raise TrajectoryValidationError("case_id missing on all events", path=path)
        if case_ids != {expected_case_id}:
            raise TrajectoryValidationError(
                f"case_id {sorted(case_ids)} != expected {expected_case_id!r}",
                path=path,
            )
    if require_terminal_run_event:
        terminals = [row.event_type for row in records if row.event_type in _TERMINAL_EVENTS]
        if not terminals:
            raise TrajectoryValidationError(
                "completed run must include RUN_COMPLETED or RUN_FAILED",
                path=path,
            )
    return records


def validate_evidence_references(records: list[TrajectoryRecord]) -> None:
    """Evidence IDs must be non-empty strings when present. Artifacts are optional."""
    for record in records:
        for eid in record.evidence_ids:
            if not isinstance(eid, str) or not eid.strip():
                raise TrajectoryValidationError(f"invalid evidence_id on {record.event_id}")


def _validate_record(
    record: TrajectoryRecord, *, path: Path, require_case_id: bool = True
) -> None:
    required = (
        record.event_id,
        record.run_id,
        record.timestamp,
        record.event_type,
        record.actor or record.agent_id,
        record.status,
    )
    if any(item is None or item == "" for item in required):
        raise TrajectoryValidationError("required event fields missing", path=path)
    if record.sequence is None:
        raise TrajectoryValidationError("sequence is required", path=path)
    if record.event_type not in VALID_EVENT_TYPES:
        raise TrajectoryValidationError(
            f"invalid event_type {record.event_type!r}",
            path=path,
        )
    if require_case_id and (record.case_id is None or not str(record.case_id).strip()):
        raise TrajectoryValidationError("case_id is required", path=path)
