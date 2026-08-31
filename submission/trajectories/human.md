# Agent: `human`

## 1. Name

`human` (`HUMAN_AGENT_ID`)

## 2. Purpose

Record Accept, Reject, or Review on an explicit checkpoint. Do not modify
source data. Do not invent yhat.

This agent is implemented in `backend/app/agents/checkpoint.py`
(`apply_human_checkpoint`). The official 12-case harness does **not** call it.

Instruction text is in `AGENT_INSTRUCTIONS["human"]` and on the demo
`HUMAN_DECISION` line.

## 3. Representative case / run

Interactive demo `run_f4c8529410f148e8a6f4973abf3440ee` (catalog **001** train
window). Not an official evaluation result.

Official catalog: **zero** `HUMAN_DECISION` events across all 12 JSONL files.

## 4. Input

Pending checkpoint `ckpt-run_f4c8529410f148e8a6f4973abf3440ee` created by the
orchestrator (seq 48). Verification was `WARN`; selected model `arima`.

## 5. Relevant tools

None. `HUMAN_DECISION` has no `tool_invocation`.

## 6. Tool result

Not applicable.

## 7. Agent action

`decision=accept`. Payload: `checkpoint_status=approved`,
`source_data_unmodified=true`, `actor=human`. No human note was stored
(none invented).

## 8. Next workflow step

Orchestrator `RUN_COMPLETED` seq 51 with `continuation_of=HUMAN_DECISION`,
`accepted=true`, `final_status=completed`.

## 9. Relevant event types

`HUMAN_DECISION` (this agent). Preceding `HUMAN_CHECKPOINT_CREATED` and both
`RUN_COMPLETED` lines are `orchestrator`.

## 10. Exact sequence / event references

Artifact:
`evaluation/artifacts/human-demo/run_f4c8529410f148e8a6f4973abf3440ee/trajectory.jsonl`

| seq | event_id | agent_id | event_type | note |
|---|---|---|---|---|
| 48 | `run_f4c8529410f148e8a6f4973abf3440ee:48` | orchestrator | `HUMAN_CHECKPOINT_CREATED` | waiting_for_approval |
| 49 | `run_f4c8529410f148e8a6f4973abf3440ee:49` | orchestrator | `RUN_COMPLETED` | still waiting |
| 50 | `run_f4c8529410f148e8a6f4973abf3440ee:50` | **human** | `HUMAN_DECISION` | `accept` |
| 51 | `run_f4c8529410f148e8a6f4973abf3440ee:51` | orchestrator | `RUN_COMPLETED` | `accepted=true` |

## 11. Final outcome

Demo run `completed` after Accept. Source data unmodified.

Catalog contrast: 12× `HUMAN_CHECKPOINT_CREATED`, 0× `HUMAN_DECISION`.
