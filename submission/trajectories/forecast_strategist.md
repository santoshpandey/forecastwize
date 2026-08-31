# Agent: `forecast_strategist`

## 1. Name

`forecast_strategist` (`FORECAST_STRATEGIST_AGENT_ID`)

## 2. Purpose

Propose candidates as hypotheses. Rank with official backtest WIS. On EXP-010,
apply the frozen last/earlier fold-WIS veto (`R=5.0`). Do not emit yhat.

Instruction: seq 18 `agent-20260830T030413Z-012:18` (same text on 005).

## 3. Representative case / run

Primary: catalog **012** (robustness vetoes → `naive`).

Supporting: catalog **005** (all four models eligible → `arima`).

Run id prefix: `agent-20260830T030413Z`.

## 4. Input

Train series, horizon, frequency, diagnostics from `data_detective`, optional
context metadata, `selection_policy=exp010`, `origin_planning=model_specific`.

## 5. Relevant tools

`list_supported_models`, `evaluate_candidates`, `analyze_backtest_robustness`.

## 6. Tool result

**012** backtest (seq 23): all four models official-eligible. Robustness
(seq 24): `threshold_r=5.0`. Vetoes (seq 26–28): seasonal_naive ratio ≈8.70,
ets ≈17.00, arima ≈40.61. Naive remains selectable (ratio ≈1.07).

**005** backtest (seq 23): arima official WIS ≈0.216 (lowest). No vetoes.
`MODEL_SELECTED` arima (seq 29).

## 7. Agent action

Record per-model eligibility or veto, then `MODEL_SELECTED` from survivors by
official backtest WIS (`selection_rule=official_backtest_wis`).

## 8. Next workflow step

FORECAST (`orchestrator` `FORECAST_STARTED` with the selected model).

## 9. Relevant event types

`AGENT_STARTED`, `AGENT_DECISION`, `TOOL_COMPLETED`, `BACKTEST_COMPLETED`,
`ROBUSTNESS_ANALYZED`, `MODEL_ELIGIBLE`, `MODEL_VETOED`, `MODEL_SELECTED`,
`AGENT_COMPLETED`.

## 10. Exact sequence / event references

**012** — `evaluation/results/trajectories/agent-20260830T030413Z/case_012.jsonl`

| seq | event_id | event_type | note |
|---|---|---|---|
| 18 | `agent-20260830T030413Z-012:18` | `AGENT_STARTED` | |
| 21 | `agent-20260830T030413Z-012:21` | `TOOL_COMPLETED` | `list_supported_models` |
| 22 | `agent-20260830T030413Z-012:22` | `TOOL_COMPLETED` | `evaluate_candidates` |
| 23 | `agent-20260830T030413Z-012:23` | `BACKTEST_COMPLETED` | four models |
| 24 | `agent-20260830T030413Z-012:24` | `ROBUSTNESS_ANALYZED` | `analyze_backtest_robustness`, `R=5.0` |
| 25 | `agent-20260830T030413Z-012:25` | `MODEL_ELIGIBLE` | `naive`, selectable |
| 26 | `agent-20260830T030413Z-012:26` | `MODEL_VETOED` | `seasonal_naive` |
| 27 | `agent-20260830T030413Z-012:27` | `MODEL_VETOED` | `ets` |
| 28 | `agent-20260830T030413Z-012:28` | `MODEL_VETOED` | `arima` |
| 29 | `agent-20260830T030413Z-012:29` | `MODEL_SELECTED` | `naive` |
| 31 | `agent-20260830T030413Z-012:31` | `AGENT_COMPLETED` | `recommended_strategy_id=naive` |

**005 ARIMA** — `evaluation/results/trajectories/agent-20260830T030413Z/case_005.jsonl`

| seq | event_id | event_type | note |
|---|---|---|---|
| 23 | `agent-20260830T030413Z-005:23` | `BACKTEST_COMPLETED` | arima lowest official WIS |
| 25–28 | `agent-20260830T030413Z-005:25` … `:28` | `MODEL_ELIGIBLE` | naive, seasonal_naive, ets, arima |
| 29 | `agent-20260830T030413Z-005:29` | `MODEL_SELECTED` | `arima` |

Evidence on 012 eligibility/veto/selected lines: `E4`, `E5`. `retry_number=0`.

## 11. Final outcome

012: selected `naive` after three vetoes. 005: selected `arima`. Deterministic
Python produced the WIS and veto; the agent only recorded them.
