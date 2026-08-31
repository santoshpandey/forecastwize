# Agent: `orchestrator`

## 1. Name

`orchestrator` (`ORCHESTRATOR_AGENT_ID`)

## 2. Purpose

Run the explicit graph: PROFILE → DIAGNOSE → CONTEXT → STRATEGY → BACKTEST →
FORECAST → VERIFY → RETRY_OR_ACCEPT → ANALYZE → FINALIZE. Verification is
required before accept. Retries are capped at 2. The orchestrator does not
emit yhat.

Instruction on catalog 005 seq 0:
`agent-20260830T030413Z-005:0` `agent_instruction` (node START).

## 3. Representative case / run

Primary: official catalog **005**, run `agent-20260830T030413Z-005`.

Supporting: catalog **003** (FAIL, no retry); demo
`run_f4c8529410f148e8a6f4973abf3440ee` (human Accept continuation).

## 4. Input

Catalog 005: `selection_policy=exp010`, `origin_planning=model_specific`,
frequency `D`, horizon 14. Payload on seq 0.

## 5. Relevant tools

- `inspect_series` (PROFILE)
- `forecast_fit` (FORECAST)

Child agents are invoked as graph nodes; their tools are on their own
`agent_id` lines.

## 6. Tool result

- Seq 2: `inspect_series` `TOOL_COMPLETED` (`agent-20260830T030413Z-005:2`,
  evidence `E2`).
- Seq 33: `forecast_fit` `FORECAST_COMPLETED` for model `arima`
  (`agent-20260830T030413Z-005:33`, evidence `E18`).

## 7. Agent action

Advance nodes. After verifier `WARN`, record `RETRY_NOT_REQUIRED` (no
strategy swap). After analyst, open a human checkpoint (low confidence).
Do not auto-approve.

## 8. Next workflow step

Seq 1 `next_step=PROFILE`. Seq 38 `next_step=ANALYZE`. After seq 49 the
catalog run stops at `waiting_for_approval` (no `HUMAN_DECISION` in this
file).

## 9. Relevant event types

`RUN_STARTED`, `AGENT_DECISION`, `TOOL_COMPLETED`, `FORECAST_STARTED`,
`FORECAST_COMPLETED`, `RETRY_NOT_REQUIRED`, `HUMAN_CHECKPOINT_CREATED`,
`RUN_COMPLETED`.

## 10. Exact sequence / event references

Artifact: `evaluation/results/trajectories/agent-20260830T030413Z/case_005.jsonl`

| seq | event_id | event_type | note |
|---|---|---|---|
| 0 | `agent-20260830T030413Z-005:0` | `RUN_STARTED` | exp010, case 005 |
| 1 | `agent-20260830T030413Z-005:1` | `AGENT_DECISION` | `next_step=PROFILE` |
| 2 | `agent-20260830T030413Z-005:2` | `TOOL_COMPLETED` | tool `inspect_series` |
| 17 | `agent-20260830T030413Z-005:17` | `AGENT_DECISION` | node STRATEGY |
| 32 | `agent-20260830T030413Z-005:32` | `FORECAST_STARTED` | model `arima` |
| 33 | `agent-20260830T030413Z-005:33` | `FORECAST_COMPLETED` | tool `forecast_fit` |
| 38 | `agent-20260830T030413Z-005:38` | `RETRY_NOT_REQUIRED` | `overall=WARN`, `retry_number=0` |
| 48 | `agent-20260830T030413Z-005:48` | `HUMAN_CHECKPOINT_CREATED` | waiting_for_approval |
| 49 | `agent-20260830T030413Z-005:49` | `RUN_COMPLETED` | `selected_model=arima`, `retry_count=0` |

FAIL-without-retry (catalog 003):

| seq | event_id | event_type |
|---|---|---|
| 38 | `agent-20260830T030413Z-003:38` | `HUMAN_CHECKPOINT_CREATED` (verification FAIL; ets not better WIS than arima) |

Demo continuation (after Accept):

| seq | event_id | event_type |
|---|---|---|
| 48 | `run_f4c8529410f148e8a6f4973abf3440ee:48` | `HUMAN_CHECKPOINT_CREATED` |
| 49 | `run_f4c8529410f148e8a6f4973abf3440ee:49` | `RUN_COMPLETED` (`waiting_for_approval`) |
| 51 | `run_f4c8529410f148e8a6f4973abf3440ee:51` | `RUN_COMPLETED` (`continuation_of=HUMAN_DECISION`, `decision=accept`) |

## 11. Final outcome

Catalog 005: `status=waiting_for_approval`, selected `arima`, verification
`WARN`, `retry_count=0`. No human decision in the official file.
