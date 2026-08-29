# EXP-007 Retry only if official backtest WIS improves

- **Kind:** iteration
- **Status:** executed
- **Date:** 2026-08-29
- **Decision:** **Keep**

## Analyze

After EXP-006, case **003** still had agent holdout WIS **−5.15** vs baseline.
The agent backtest ranked `seasonal_naive` first, then verification FAIL
retried `_next_strategy` and fitted **naive** (worse official backtest WIS).
Rank-1 was already the WIS winner; swapping on FAIL was not a measured
improvement.

Compared to: `evaluation/artifacts/EXP-006-missing-policy/comparison.json`
(`comparison-20260829T124600Z`).

## Hypothesis

If verification FAIL retries **only** when the next untried model has
**strictly lower** official backtest WIS than the current selection, case 003
will keep `seasonal_naive` and match baseline holdout WIS. A worse-WIS swap
will not run. Missing numeric WIS on either side will not retry.

## Implement

`_node_retry_or_accept` in `backend/app/agents/orchestrator.py` uses
`_next_better_wis_strategy`. Trajectory records current vs next official WIS
when a retry is allowed; otherwise the checkpoint reason states that a worse
model was not selected.

## Test

`backend/tests/test_orchestrator.py`: FAIL with a worse untried model does
not retry; FAIL then PASS only when the alternative has better backtest WIS;
retry cap still exhausts on an improving-WIS chain.

## Run same benchmark

```powershell
python evaluation/run_baseline.py --output-json evaluation/artifacts/EXP-007-retry-backtest-wis/baseline.json --output-md evaluation/artifacts/EXP-007-retry-backtest-wis/baseline.md
python evaluation/run_agent.py --output-json evaluation/artifacts/EXP-007-retry-backtest-wis/agent.json --output-md evaluation/artifacts/EXP-007-retry-backtest-wis/agent.md
python evaluation/compare.py --baseline evaluation/artifacts/EXP-007-retry-backtest-wis/baseline.json --agent evaluation/artifacts/EXP-007-retry-backtest-wis/agent.json --output-json evaluation/artifacts/EXP-007-retry-backtest-wis/comparison.json
```

## Compare

| Field | EXP-006 | EXP-007 |
|---|---|---|
| `comparison_id` | `comparison-20260829T124600Z` | `comparison-20260829T125037Z` |
| Baseline / agent run ids | `baseline-20260829T124522Z` / `agent-20260829T124543Z` | `baseline-20260829T124957Z` / `agent-20260829T125021Z` |
| Official WIS baseline | 0.9153 | 0.9153 |
| Official WIS agent | 1.1343 | **0.9476** |
| `wis.relative_improvement` | −0.2392 | **−0.0352** |
| Case 003 WIS relative | −5.15 | **0.0** (both `seasonal_naive`) |
| Case 003 `retry_number` | 1 | **0** |
| Cases 009 / 010 | still agent WIS losses | unchanged (still shortlist backtest) |

Agent remains slightly worse than baseline on official catalog WIS. No case
was dropped. Catalog CSVs were not edited.

## Keep / Remove

**Keep.** The change recovered case 003 to parity with baseline and improved
official agent WIS vs EXP-006 without claiming a win over the conventional
harness.

## Document

This record. Agent design: FAIL retries only on better official backtest WIS.

## Problem observed

Verification FAIL swapped 003 from rank-1 `seasonal_naive` to worse `naive`.

## Change made

Retry only if the next untried model has strictly lower official backtest WIS.

## Evaluation command

Same three commands as **Run same benchmark**.

## Baseline result

`evaluation/artifacts/EXP-007-retry-backtest-wis/baseline.json`
`evaluation_run_id`: `baseline-20260829T124957Z`
Official aggregate WIS **0.9153325914744158**.

## New result

`evaluation/artifacts/EXP-007-retry-backtest-wis/agent.json`
`evaluation_run_id`: `agent-20260829T125021Z`
Official aggregate WIS **0.947558571288425**.

## Improvement

Vs EXP-006, agent official WIS 1.1343 → 0.9476. Vs baseline,
`wis.relative_improvement` **−0.0352**. Case 003 WIS relative **0.0**.
Not an official win over baseline.

## Failure cases

None. 009/010 still lost (shortlist backtest).

## Decision

**Keep.**

## Lesson learned

A verifier FAIL is not evidence that a worse backtest model is better on
holdout. Retry needs a strictly better official backtest WIS.
