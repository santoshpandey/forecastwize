# Agent: `verifier`

## 1. Name

`verifier` (`VERIFIER_AGENT_ID`)

## 2. Purpose

Challenge the forecast with deterministic checks. Do not emit or adjust yhat.

Instruction: seq 34 `agent-20260830T030413Z-005:34`.

## 3. Representative case / run

Official catalog **005**, run `agent-20260830T030413Z-005`. Overall `WARN`.

Supporting: catalog **003** overall `FAIL` (no retry; see orchestrator note).

## 4. Input

Train values/timestamps and the `forecast_fit` artifact for the selected model
(`arima` on 005).

## 5. Relevant tools

`verify_forecast` only.

## 6. Tool result

Seq 36 payload `overall=WARN`. Checks (abbrev.): V10/V01/V02/V03/V04/V07/V09
PASS; V05 residual WARN; V06 interval coverage WARN; V08 regime-change WARN.
`retry_recommended=false`.

## 7. Agent action

Report the challenge result. Does not select a new model.

## 8. Next workflow step

RETRY_OR_ACCEPT. On 005 that is `RETRY_NOT_REQUIRED` then ANALYZE.

## 9. Relevant event types

`VERIFICATION_STARTED`, `TOOL_COMPLETED`, `VERIFICATION_COMPLETED`.

## 10. Exact sequence / event references

Artifact: `evaluation/results/trajectories/agent-20260830T030413Z/case_005.jsonl`

| seq | event_id | event_type | note |
|---|---|---|---|
| 34 | `agent-20260830T030413Z-005:34` | `VERIFICATION_STARTED` | model `arima`, `n_forecast=14` |
| 35 | `agent-20260830T030413Z-005:35` | `TOOL_COMPLETED` | `verify_forecast` |
| 36 | `agent-20260830T030413Z-005:36` | `VERIFICATION_COMPLETED` | child; checks listed |
| 37 | `agent-20260830T030413Z-005:37` | `VERIFICATION_COMPLETED` | graph ingest; `overall=WARN` |

**003 FAIL** — `case_003.jsonl` seq 36–37
`agent-20260830T030413Z-003:36` `overall=FAIL`, `retry_recommended=true`.
The orchestrator still did not emit `RETRY_REQUESTED` (ets not better WIS).

## 11. Final outcome

005: challenge stands at `WARN`. Forecast numbers unchanged. Graph does not
retry.
