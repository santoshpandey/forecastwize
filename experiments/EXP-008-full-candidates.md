# EXP-008 Backtest the full baseline candidate set

- **Kind:** iteration
- **Status:** executed
- **Date:** 2026-08-29
- **Decision:** **Keep**

## Analyze

After EXP-007, cases **009** and **010** still lost on holdout WIS because the
orchestrator backtested only `propose_candidate_ids` (typically `naive` when
seasonality was not flagged). The eval harness already passed
`BASELINE_MODEL_IDS` (`naive`, `seasonal_naive`, `ets`, `arima`); the STRATEGY
node filtered that list down to the shortlist, then BACKTEST executed only
those ids. Baseline always backtested all four.

Compared to: `evaluation/artifacts/EXP-007-retry-backtest-wis/comparison.json`
(`comparison-20260829T125037Z`).

## Hypothesis

If BACKTEST executes the full allow-list (eval: the same four models as
baseline) and STRATEGY’s shortlist stays a **hypothesis** only, 009 and 010
will select the same official-WIS winner as baseline and those WIS gaps will
close.

## Implement

`_node_backtest` in `backend/app/agents/orchestrator.py` uses
`_backtest_model_ids` (`ctx.candidate_model_ids` or `BASELINE_MODEL_IDS`).
`proposed_candidate_ids` remain recorded; they no longer restrict execution.

## Test

`test_backtest_executes_allowlist_not_strategy_shortlist`: strategy proposes
only `naive`; hooked backtest receives all four `BASELINE_MODEL_IDS`.

## Run same benchmark

```powershell
python evaluation/run_baseline.py --output-json evaluation/artifacts/EXP-008-full-candidates/baseline.json --output-md evaluation/artifacts/EXP-008-full-candidates/baseline.md
python evaluation/run_agent.py --output-json evaluation/artifacts/EXP-008-full-candidates/agent.json --output-md evaluation/artifacts/EXP-008-full-candidates/agent.md
python evaluation/compare.py --baseline evaluation/artifacts/EXP-008-full-candidates/baseline.json --agent evaluation/artifacts/EXP-008-full-candidates/agent.json --output-json evaluation/artifacts/EXP-008-full-candidates/comparison.json
```

## Compare

| Field | EXP-007 | EXP-008 |
|---|---|---|
| `comparison_id` | `comparison-20260829T125037Z` | `comparison-20260829T125254Z` |
| Baseline / agent run ids | `baseline-20260829T124957Z` / `agent-20260829T125021Z` | `baseline-20260829T125209Z` / `agent-20260829T125231Z` |
| Official WIS (both) | baseline 0.9153 / agent 0.9476 | **0.9153 / 0.9153** |
| `wis.relative_improvement` | −0.0352 | **0.0** |
| Case 009 | agent naive, WIS −0.55 | both `seasonal_naive`, WIS **0.0** |
| Case 010 | agent naive, WIS −0.18 | both `seasonal_naive`, WIS **0.0** |
| Human interventions | 12 | 12 |

No completed case has agent WIS **better** than baseline. Parity is not an
official WIS win. Catalog CSVs were not edited. Agent 009/010 backtest
snapshots include all four model ids.

## Keep / Remove

**Keep.** The agent now uses the same candidate set and selection rule as the
baseline on these cases. Do not headline a WIS improvement; `relative_improvement`
is **0**.

## Document

This record. Current `evaluation/results/*.json` is a copy of this pair (see
changelog). Agent design: shortlist is hypothesis; backtest executes the
allow-list.

## Hypothesis

(See Analyze / Hypothesis above.)

## Problem observed

Strategy shortlist was executed as the backtest set, so 009/010 never saw
`seasonal_naive` even though baseline did.

## Change made

BACKTEST runs `BASELINE_MODEL_IDS` (or the caller allow-list), not
`proposed_candidate_ids`.

## Evaluation command

Same three commands as **Run same benchmark**.

## Baseline result

`evaluation/artifacts/EXP-008-full-candidates/baseline.json`
`evaluation_run_id`: `baseline-20260829T125209Z`
Official aggregate WIS **0.9153325914744158**; `n_cases_failed` 0.

## New result

`evaluation/artifacts/EXP-008-full-candidates/agent.json`
`evaluation_run_id`: `agent-20260829T125231Z`
Official aggregate WIS **0.9153325914744158**; `n_cases_failed` 0;
`human_intervention_count` 12.

## Improvement

`comparison-20260829T125254Z` `aggregate.metrics.wis.relative_improvement`
is **0.0**. Vs EXP-007, agent official WIS improved from 0.9476 to 0.9153
(parity with baseline). That is not a win over the conventional system.

## Failure cases

None in this pair (`errors` empty). All 12 cases completed.

## Decision

**Keep.**

## Lesson learned

A hypothesis shortlist must not shrink the executed candidate set if the
baseline is scored on the full allow-list. Selection remains official backtest
WIS; the LLM still does not emit yhat.
