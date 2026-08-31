# Agent: `context_analyst`

## 1. Name

`context_analyst` (`CONTEXT_ANALYST_AGENT_ID`)

## 2. Purpose

Record observed event/context labels as facts. Do not infer causality. Do not
adjust forecasts.

Instruction: seq 13 `agent-20260830T030413Z-005:13`.

## 3. Representative case / run

- Catalog **005**: no context labels (`context_available=false`).
- Catalog **012**: labels present (`context_available=true`).

Both are official `agent-20260830T030413Z`.

## 4. Input

Optional event/context label series from the case CSV, plus timestamps. Case
005 has no usable labels. Case 012 does.

## 5. Relevant tools

`inspect_context` only.

## 6. Tool result

`TOOL_COMPLETED` on seq 14 in both files. The structured flag is on the
following `AGENT_COMPLETED` ingest line.

## 7. Agent action

Write observed-fact claims when labels exist. Otherwise record that context
is unavailable. No forecast change.

## 8. Next workflow step

STRATEGY (`orchestrator` `AGENT_DECISION`), then `forecast_strategist`.

## 9. Relevant event types

`AGENT_STARTED`, `TOOL_COMPLETED`, `AGENT_COMPLETED`.

## 10. Exact sequence / event references

**005** — `evaluation/results/trajectories/agent-20260830T030413Z/case_005.jsonl`

| seq | event_id | event_type | note |
|---|---|---|---|
| 13 | `agent-20260830T030413Z-005:13` | `AGENT_STARTED` | |
| 14 | `agent-20260830T030413Z-005:14` | `TOOL_COMPLETED` | tool `inspect_context` |
| 15 | `agent-20260830T030413Z-005:15` | `AGENT_COMPLETED` | child complete |
| 16 | `agent-20260830T030413Z-005:16` | `AGENT_COMPLETED` | payload `context_available=false` |

**012** — `evaluation/results/trajectories/agent-20260830T030413Z/case_012.jsonl`

| seq | event_id | event_type | note |
|---|---|---|---|
| 13 | `agent-20260830T030413Z-012:13` | `AGENT_STARTED` | |
| 14 | `agent-20260830T030413Z-012:14` | `TOOL_COMPLETED` | tool `inspect_context` |
| 16 | `agent-20260830T030413Z-012:16` | `AGENT_COMPLETED` | payload `context_available=true` |

## 11. Final outcome

Context facts recorded or explicitly absent. Graph proceeds to strategy /
backtest unchanged.
