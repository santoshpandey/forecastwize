# Agent trajectories

Append-only **JSONL** (one JSON object per line) for every agent run. Child agents
are usually called with `persist_trajectory=False`; `run_orchestrator` owns the
run file. Pytest writes under a temp path unless a test points here.

## Layout

```
trajectories/
  {run_id}.jsonl              # steps for one run
  artifacts/{run_id}/A-*.json # tool payloads referenced from those steps
```

Do not put secrets, API keys, or raw training series in these files. Tool
outputs live in `artifacts/` and are referenced from the JSONL line
(`tool_output_ref`). Forecast `yhat` belongs in a forecast-fit artifact, not in
the trajectory line.

## Record fields

Each line is a `TrajectoryRecord` (`backend/app/evidence/trajectory.py`):

| Field | Meaning |
|---|---|
| `run_id` | Overall run |
| `agent_id` | Agent or graph node owner |
| `timestamp` | UTC ISO 8601 |
| `agent_instruction` | What this agent is allowed to do |
| `input_state_hash` | SHA-256 of the redacted input summary |
| `input_summary` | Counts, frequency, node, strategy — not series values |
| `tool_invocation` | Approved tool name + argument summary, or null |
| `tool_output_ref` | Artifact id + sha256, or null |
| `decision` | Structured decision for this step |
| `evidence_ids` | IDs cited for material claims |
| `retry_number` | 0-based, within the retry cap |
| `status` / `final_status` | `running`, `retrying`, `completed`, `failed`, `waiting_for_approval` |
| `next_step` | Following node or action, or null at a terminal status |
| `error` | `error_type` + redacted `error_message` when the step failed |
| `final_result` | Compact outcome on completed / failed / waiting_for_approval |

Compatibility aliases `input_state`, `tool_requested`, and `tool_result`
(compact pointer, not a payload dump) stay on the line so older tests still
read the file.

## Reviewer sequence

A reviewer should be able to follow:

`agent_instruction` → `input_summary` → `tool_invocation` → `tool_output_ref`
→ `decision` → `next_step` → `final_result`

Representative checked-in examples:
`backend/tests/fixtures/trajectories/*.jsonl`.

Runtime files in this directory are gitignored except this README and `.gitkeep`.
