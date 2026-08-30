# EXP-010 Robust model selection

- **Kind:** iteration
- **Status:** executed (successful on official aggregate WIS)
- **Date:** 2026-08-30
- **Decision:** **Promoted** to the official advanced solution. See
  [EXP-010-PROMOTION.md](EXP-010-PROMOTION.md). Frozen isolate remains
  `evaluation/artifacts/EXP-010-robust-model-selection/`. Do **not** retune
  `R`. Official default is `selection_policy=exp010` (no flag required).

## Hypothesis

Historical official backtest WIS alone is insufficient when fold WIS is
unstable or a regime change hits late training/test windows.

If the advanced path (1) plans model-specific valid expanding origins and
(2) applies a deterministic last/earlier fold-WIS veto (`R=5`, frozen from
EXP-009 **training** fold tables), ARIMA wins on stable series can be kept
while ETS is refused on the EXP-009 012 failure mode.

The LLM must not invent these statistics or the ranking.

## Problem observed

EXP-009 made ETS/ARIMA officially eligible. Catalog official WIS rose from
0.915 to 2.437 because case **012** selected ETS (holdout WIS 22.83). Fold
evidence already showed ETS last/earlier ≈ 17. See
[EXP-009](EXP-009-ets-arima-min-train.md) and the analysis below.

## Change made

**Baseline:** unchanged (`run_rolling_origin_backtest`).

**Advanced (opt-in `--selection-policy exp010` only):**

- Reuses EXP-009 `origin_planning='model_specific'`.
- New deterministic tool `analyze_backtest_robustness` computes fold mean /
  median / std / min / max, last-fold mean, earlier-fold mean, last/earlier
  ratio, and optional aligned fold-win counts. No holdout. No yhat.
- Frozen `EXP010_LAST_TO_EARLIER_VETO = 5.0` (chosen from EXP-009 train
  tables before this catalog run; not retuned afterward).
- Selectable models: official WIS finite, no failed planned folds, and
  last/earlier `< 5` when the ratio is defined.
- Rank remaining models by official backtest WIS.
- If every official-eligible model is vetoed: lowest last-fold WIS fallback
  (`last_fold_wis_fallback`).
- Orchestrator retries skip `selectable=False` models.
- After promotion, default `run_agent.py` is this policy.

No WIS formula change. No case catalog change. No holdout in selection.

## Baseline behavior

Shared expanding origins. Same first origin for every candidate.

## Advanced behavior

Model-specific first origins plus the instability veto. Structural-break
flags remain diagnostic context; there is no “if break then seasonal naive”
rule.

## Evidence

Robustness payload and comparison rows record: official WIS, fold WIS, train
sizes, last/earlier ratio, veto, selectable, rejection reason, selection
rule. Trajectory records the real `analyze_backtest_robustness` tool when
`persist_trajectory=True`.

**Historical (this isolated run, before the observability phase):** the
EXP-010 isolate under `evaluation/artifacts/EXP-010-robust-model-selection/`
was executed with catalog persist off. That is not the current official
harness setting.

**Current official catalog evaluation:** `python evaluation/run_agent.py`
defaults to `persist_trajectory=True` and writes 12 case JSONL files under
`evaluation/results/trajectories/<evaluation_run_id>/`.

## Evaluation command

```powershell
python evaluation/run_baseline.py --output-json evaluation/artifacts/EXP-010-robust-model-selection/baseline.json --output-md evaluation/artifacts/EXP-010-robust-model-selection/baseline.md
python evaluation/run_agent.py --selection-policy exp010 --output-json evaluation/artifacts/EXP-010-robust-model-selection/agent.json --output-md evaluation/artifacts/EXP-010-robust-model-selection/agent.md
python evaluation/compare.py --baseline evaluation/artifacts/EXP-010-robust-model-selection/baseline.json --agent evaluation/artifacts/EXP-010-robust-model-selection/agent.json --output-json evaluation/artifacts/EXP-010-robust-model-selection/comparison.json
```

Isolated directory: `evaluation/artifacts/EXP-010-robust-model-selection/`.
Did **not** overwrite `evaluation/results/`. `R` was not changed after this
run.

## Baseline result

| Field | Value |
|---|---|
| `evaluation_run_id` | `baseline-20260830T014058Z` |
| Official WIS | **0.9153325914744158** |
| `n_cases_failed` | 0 |

Matches the official baseline WIS.

## New result

| Field | Value |
|---|---|
| `evaluation_run_id` | `agent-20260830T014147Z` |
| `comparison_id` | `comparison-20260830T014245Z` |
| Official WIS | **0.7939144093884205** |
| `n_cases_failed` | 0 |
| Human interventions | 12 |
| `origin_planning` | `model_specific` |
| `selection_policy` | `exp010` |
| Wall seconds | ~28.4 (baseline ~20.5) |

`case_lists_identical`: true. All 12 cases evaluated.

## Improvement

**Yes on the headline metric.**

`wis.relative_improvement` = **0.13264925035654543** (agent better).

Case wins (holdout WIS): agent **8**, baseline **2**, ties **2**.

## Per-case comparison

Retries were 0 on every case.

| Case | Baseline WIS | Agent WIS | Winner | Rel. impr. | Baseline model | Agent model | Notes |
|---|---|---|---|---|---|---|---|
| 001 | 0.4549 | 0.0481 | agent | 0.894 | naive | **arima** | No veto; ARIMA official WIS rank-1 |
| 002 | 0.1323 | 0.0905 | agent | 0.316 | seasonal_naive | **arima** | |
| 003 | 0.4355 | 0.1251 | agent | 0.713 | seasonal_naive | **arima** | VERIFY FAIL; no better selectable official WIS |
| 004 | 4.0463 | 2.4555 | agent | 0.393 | naive | **arima** | |
| 005 | 0.3789 | 0.1636 | agent | 0.568 | seasonal_naive | **arima** | ARIMA ratio 1.53; below R=5 |
| 006 | 1.3731 | 1.3731 | tie | 0.000 | naive | naive | |
| 007 | 0.3088 | 0.3762 | baseline | −0.218 | naive | seasonal_naive | Same side-effect as EXP-009 naive 1-obs folds |
| 008 | 0.3389 | 0.2745 | agent | 0.190 | seasonal_naive | **arima** | |
| 009 | 0.4185 | 0.3779 | agent | 0.097 | seasonal_naive | **arima** | |
| 010 | 0.8924 | 0.8924 | tie | 0.000 | seasonal_naive | seasonal_naive | ETS/ARIMA insufficient history |
| 011 | 0.8262 | 0.2358 | agent | 0.715 | seasonal_naive | **arima** | |
| 012 | 1.3781 | 3.1143 | baseline | −1.260 | seasonal_naive | **naive** | ETS/SN/ARIMA vetoed; catastrophe avoided |

012 veto ratios (training folds): ETS **17.00**, seasonal_naive **8.70**,
ARIMA **40.61**, naive **1.07**. Holdout naive WIS **3.114** vs EXP-009 ETS
**22.83**. Still worse than baseline seasonal_naive, but the catalog mean
improves.

## Failure cases / failure analysis

**007** and **012** still lose holdout WIS to baseline. 012 is no longer
catastrophic. 007 is the model-specific naive short-origin ranking side
effect (official naive WIS worse than seasonal_naive). Neither loss
overturns the 12-case official mean.

No cases failed. No case removed. No holdout used in selection.

## Decision

**Promote** EXP-010 to the official advanced solution.

- Official cited pair is now `evaluation/results/comparison.json`
  (`comparison-20260830T020453Z`).
- Default `run_agent.py` is `--selection-policy exp010`.
- Frozen isolate and `R=5` are unchanged.
- Do not start EXP-011 in this change.

## Lesson learned

Official aggregate WIS can hide a single exploding last fold. A **gate** on
last/earlier fold WIS (not a weighted blend, not last-fold-only ranking)
kept the EXP-009 ARIMA wins and blocked 012 ETS. Catalog success does not
require winning every case.

## Tests

`backend/tests/test_forecasting_robustness.py` plus harness/strategist
updates.

---

## Design analysis (EXP-009 evidence; unchanged after the run)

The numbered analysis from the design pass remains the justification for
`R=5` and for not ranking by last-fold WIS alone. Source:
`evaluation/artifacts/EXP-009-ets-arima-min-train/`.

1. **ARIMA helped 001–005, 008, 009, 011** because those models became
   official-WIS-eligible and ranked first. Last/earlier ≤ 1.53.
2. **012 selected ETS** on official mean 1.378 vs SN 1.691.
3. **012 ETS holdout failed** (WIS 22.83) because no planned fold trained
   after the regime change; holdout was a different process.
4. **Fold evidence warned:** ETS `[0.38, 0.36, 0.27, 0.30, 5.58]`, ratio ≈17.
5. **Recent-fold as veto:** yes. As a replacement ranker: no (would pick ETS
   on 007).
6. **Break screen:** train-only detector fires on 012; must not hard-code SN
   (SN ratio 8.7 also vetoed).
7. **Policy on 012:** ETS not selected (naive). Confirmed in this run.
8. **ARIMA harm at R=5:** not observed; 005 ratio 1.53 still selected ARIMA.
9. **Guardrails:** frozen R, no holdout, no case IDs, no completed-only
   headline, retries skip vetoed models.
