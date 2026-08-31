# Agent: `data_detective`

## 1. Name

`data_detective` (`DATA_DETECTIVE_AGENT_ID`)

## 2. Purpose

Run approved diagnostic tools and cite evidence IDs. Do not emit yhat. Do not
modify the series.

Instruction: seq 3 `agent-20260830T030413Z-005:3`.

## 3. Representative case / run

Official catalog **005** (missing values), run `agent-20260830T030413Z-005`.

## 4. Input

Train window for case 005 after the evaluation split. Frequency and seasonal
period come from the graph. The detective does not receive holdout.

## 5. Relevant tools

`inspect_series`, `diagnose_quality`, `diagnose_outliers`,
`diagnose_rolling_anomalies`, `diagnose_trend`, `diagnose_seasonality`,
`diagnose_structural_breaks`.

## 6. Tool result

All seven calls are `TOOL_COMPLETED` (`ok` path). Compact tool payloads live
under `evaluation/results/trajectories/agent-20260830T030413Z/artifacts/`
via `tool_output_ref` on those lines.

## 7. Agent action

Screen the series, then emit a structured report. Seq 11 payload:
`forecastability=limited`, `status=completed`.

## 8. Next workflow step

Orchestrator DIAGNOSE wrapper seq 12 (`run_data_detective`), then CONTEXT
(`context_analyst` seq 13).

## 9. Relevant event types

`AGENT_STARTED`, `TOOL_COMPLETED`, `AGENT_COMPLETED`.

## 10. Exact sequence / event references

Artifact: `evaluation/results/trajectories/agent-20260830T030413Z/case_005.jsonl`

| seq | event_id | event_type | tool |
|---|---|---|---|
| 3 | `agent-20260830T030413Z-005:3` | `AGENT_STARTED` | — |
| 4 | `agent-20260830T030413Z-005:4` | `TOOL_COMPLETED` | `inspect_series` |
| 5 | `agent-20260830T030413Z-005:5` | `TOOL_COMPLETED` | `diagnose_quality` |
| 6 | `agent-20260830T030413Z-005:6` | `TOOL_COMPLETED` | `diagnose_outliers` |
| 7 | `agent-20260830T030413Z-005:7` | `TOOL_COMPLETED` | `diagnose_rolling_anomalies` |
| 8 | `agent-20260830T030413Z-005:8` | `TOOL_COMPLETED` | `diagnose_trend` |
| 9 | `agent-20260830T030413Z-005:9` | `TOOL_COMPLETED` | `diagnose_seasonality` |
| 10 | `agent-20260830T030413Z-005:10` | `TOOL_COMPLETED` | `diagnose_structural_breaks` |
| 11 | `agent-20260830T030413Z-005:11` | `AGENT_COMPLETED` | — (`status=completed`) |
| 12 | `agent-20260830T030413Z-005:12` | `AGENT_COMPLETED` | orchestrator ingest `run_data_detective` |

Evidence IDs on seq 11: `E1`–`E7`. `retry_number=0`.

## 11. Final outcome

Detective status `completed`. Graph continues to `context_analyst`. No series
mutation is recorded.
