# EXP-009 ETS/ARIMA model-specific minimum train origins

- **Kind:** iteration
- **Status:** executed (unsuccessful on official aggregate WIS)
- **Date:** 2026-08-29
- **Decision:** **Remove** from the official cited pair. Do **not** copy into
  `evaluation/results/`.

## Hypothesis

If the advanced workflow plans expanding-origin folds with each model’s
**own** minimum valid training length (the same rules `fit()` already
enforces), ETS and ARIMA will receive finite **official** backtest WIS
instead of a poisoned mean from a too-short first fold. The agent may then
select a different model than the baseline and reduce holdout WIS.

Completed-only WIS is **not** used for headline selection.

## Problem observed

On the official EXP-008 pair, every case tied. ETS/ARIMA had
`official_wis=null` because the **shared** first expanding origin used
`min_train_size` ≈ 8 while seasonal ETS needs 16 observations (2×period and
statsmodels heuristic init) and seasonal ARIMA needs 22 (`2m+8`).

## Change made

**Baseline (`evaluation/run_baseline.py`):** unchanged. Still
`run_rolling_origin_backtest` with one shared origin grid.

**Advanced:**

- Each `ForecastModel` declares `minimum_train_size(frequency=...)`.
  Naive: 1. Seasonal naive: period. ETS: `max(2m, 10+2*(m//2))` when
  seasonal (statsmodels heuristic), else 3. ARIMA: `2m+8` seasonal, else 8.
- `run_model_specific_origin_backtest` plans folds per model. Origins with
  `n_train < min` are **skipped** (planning), not failed executions.
- Target fold count remains 5, using the same step formula as the baseline
  harness on that model’s valid origin range.
- A planned fold that still fails keeps official WIS undefined.
- `evaluate_candidates` (agent/strategist) used `origin_planning=model_specific`
  during this isolated run. The product **default** was later restored to
  shared origins; reproduce this experiment with
  `--origin-planning model_specific`.
- Selection remains rank-1 **official** backtest WIS among models with
  `n_folds_planned>0` and `n_folds_failed=0`.

No WIS formula change. No case catalog change. No holdout in selection.

## Baseline behavior

Shared expanding origins. Same first origin for every candidate. ETS/ARIMA
typically fail fold 0 and cannot be selected.

## Advanced behavior

Per-model first origin. ETS/ARIMA become eligible when history is long
enough (not on case 010). Naive may start at 1 observation (side effect of
the model’s true minimum).

## Evidence

Strategist `evaluate_candidates` payload and claims record: model id,
`min_train_size`, planned/completed/failed counts, skipped short origins,
fold train sizes, fold WIS, official WIS, rank, eligibility, rejection
reason. Trajectory uses the real tool path (`persist_trajectory=False` on
catalog eval; unit tests write JSONL).

## Evaluation command

```powershell
python evaluation/run_baseline.py --output-json evaluation/artifacts/EXP-009-ets-arima-min-train/baseline.json --output-md evaluation/artifacts/EXP-009-ets-arima-min-train/baseline.md
python evaluation/run_agent.py --origin-planning model_specific --output-json evaluation/artifacts/EXP-009-ets-arima-min-train/agent.json --output-md evaluation/artifacts/EXP-009-ets-arima-min-train/agent.md
python evaluation/compare.py --baseline evaluation/artifacts/EXP-009-ets-arima-min-train/baseline.json --agent evaluation/artifacts/EXP-009-ets-arima-min-train/agent.json --output-json evaluation/artifacts/EXP-009-ets-arima-min-train/comparison.json
```

`--origin-planning model_specific` is required after the default advanced path
was restored to shared origins. Omitting the flag reproduces EXP-008 parity,
not this experiment.

Isolated directory: `evaluation/artifacts/EXP-009-ets-arima-min-train/`.
Did **not** overwrite `evaluation/results/`.

## Baseline result

| Field | Value |
|---|---|
| `evaluation_run_id` | `baseline-20260829T154533Z` |
| Official WIS | **0.9153325914744158** |
| `n_cases_failed` | 0 |
| Wall seconds | 16.62 |

Matches the existing official baseline WIS (`evaluation/results/baseline.json`,
`baseline-20260829T125209Z`).

## New result

| Field | Value |
|---|---|
| `evaluation_run_id` | `agent-20260829T154616Z` |
| `comparison_id` | `comparison-20260829T154706Z` |
| Official WIS | **2.437026585640708** |
| `n_cases_failed` | 0 |
| Human interventions | 12 |
| Wall seconds | 25.30 |

`case_lists_identical`: true. All 12 cases evaluated.

## Improvement

**None on the headline metric.**

`wis.relative_improvement` = **−1.662449265261221** (agent worse).

Case wins (WIS): agent **8**, baseline **2**, ties **2**.

Eight per-case wins do **not** count as success. Case **012** holdout WIS
1.378 → **22.832** (`relative_improvement` **−15.57**) dominates the mean.

## Per-case comparison

Winner is holdout WIS (lower better). Retries were 0 on every case.

| Case | Baseline WIS | Agent WIS | Winner | Rel. impr. | Baseline model | Agent model | Verify | Notes |
|---|---|---|---|---|---|---|---|---|
| 001 | 0.4549 | 0.0481 | agent | 0.894 | naive | **arima** | WARN | ETS/ARIMA eligible; ARIMA rank-1 |
| 002 | 0.1323 | 0.0905 | agent | 0.316 | seasonal_naive | **arima** | WARN | |
| 003 | 0.4355 | 0.1251 | agent | 0.713 | seasonal_naive | **arima** | FAIL | FAIL did not retry (rank-1 already best official WIS) |
| 004 | 4.0463 | 2.4555 | agent | 0.393 | naive | **arima** | WARN | |
| 005 | 0.3789 | 0.1636 | agent | 0.568 | seasonal_naive | **arima** | WARN | |
| 006 | 1.3731 | 1.3731 | tie | 0.000 | naive | naive | WARN | ARIMA eligible but worse official WIS |
| 007 | 0.3088 | 0.3762 | baseline | −0.218 | naive | seasonal_naive | WARN | Naive’s 1-obs fold worsened its backtest WIS vs shared plan |
| 008 | 0.3389 | 0.2745 | agent | 0.190 | seasonal_naive | **arima** | WARN | |
| 009 | 0.4185 | 0.3779 | agent | 0.097 | seasonal_naive | **arima** | WARN | |
| 010 | 0.8924 | 0.8924 | tie | 0.000 | seasonal_naive | seasonal_naive | WARN | ETS/ARIMA `insufficient_history` (planned=0, not failed folds) |
| 011 | 0.8262 | 0.2358 | agent | 0.715 | seasonal_naive | **arima** | WARN | |
| 012 | 1.3781 | 22.8317 | baseline | −15.57 | seasonal_naive | **ets** | FAIL | Backtest picked ETS; holdout MAE 42 vs 2.96 |

Eligibility: ETS min_train=16 and ARIMA min_train=22 on daily seasonal cases;
both official-WIS-eligible except 010.

## Failure cases / failure analysis

**Headline failure:** official 12-case mean WIS.

**012 (adversarial regime):** ETS had the lowest **train** rolling-origin WIS
(1.378 vs seasonal_naive 1.691) and was selected. Holdout is a different
regime. ETS extrapolated badly (coverage 0.357, MAE 42.16). Verification
FAIL; no better-official-WIS alternative to retry to. This is
**backtest/holdout mismatch**, not a WIS-formula bug and not a leakage bug.

**007:** Shared-origin baseline keeps naive. Agent naive backtest includes a
**1-observation** fold, so official naive WIS rose and seasonal_naive won
selection; holdout WIS slightly worse.

**010:** Hypothesis correctly predicts ETS/ARIMA cannot be planned; tie.

The hypothesis that ETS/ARIMA **eligibility** would help 001/002/003/011
**was supported on those cases**. It was **falsified as a catalog-mean
strategy** because 012’s loss swamps those gains.

## Decision

**Remove** as the official advanced evaluation story.

- Do not overwrite this frozen pair. EXP-009 is **not** successful.
- Official cited pair at the time of this experiment was EXP-008
  (`relative_improvement` **0.0**). After EXP-010 promotion, official is
  EXP-010 — still not this pair.
- Do not change WIS, cases, or the baseline engine to manufacture a win.
- Implementation of model-specific planning remains as a historical opt-in
  (`python evaluation/run_agent.py --origin-planning model_specific`).
  That command does **not** use the current official default.

## Lesson learned

Making ETS/ARIMA officially rankable is necessary but not sufficient.
Official backtest WIS on expanding full-history folds can prefer a model
that is catastrophic after a regime change (012). A 1-observation naive
fold is a legal `fit` and distorts ranking (007). Catalog-mean WIS is the
only headline; eight case wins plus one disaster is a **loss**.

## Tests

See `backend/tests/test_forecasting_min_train.py` and
`backend/tests/test_forecasting_model_specific_backtest.py`.
