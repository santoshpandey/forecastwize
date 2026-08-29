# EXP-INITIAL-COMPARISON First complete baseline vs advanced catalog run

- **Kind:** final
- **Status:** executed
- **Date:** 2026-08-29

This is the first complete paired catalog run of the graph
(diagnostics, backtest selection, verifier, bounded retry, human checkpoint),
**before** EXP-006–008. Algorithms were **not** changed to chase scores.

`evaluation/results/*.json` was later replaced by the EXP-008 copy. Frozen
files for **this** experiment: `evaluation/artifacts/exp-initial-comparison/`.

## Hypothesis

On the shared 12-case catalog, the orchestrated advanced path would improve
official holdout **WIS** versus the conventional baseline that selects by
expanding-window backtest WIS and then fits the winner.

## Problem observed

Prior named records either measured an earlier pair (EXP-005) or were
unmeasured iterations (EXP-002–004, checkpoints). A fresh triple
`run_baseline` / `run_agent` / `compare` was required so claims match the
files that were then in `evaluation/results/` (now frozen under
`evaluation/artifacts/exp-initial-comparison/`).

## Change made

**None to forecasting or agent algorithms for this experiment.** The commands
below were executed as written.

## Evaluation command

From the repository root:

```powershell
python evaluation/run_baseline.py
python evaluation/run_agent.py
python evaluation/compare.py
```

Generated artifacts (this run; frozen under
`evaluation/artifacts/exp-initial-comparison/`):

| File | Id |
|---|---|
| `evaluation/artifacts/exp-initial-comparison/baseline.json` | `baseline-20260829T123106Z` |
| `evaluation/artifacts/exp-initial-comparison/agent.json` | `agent-20260829T123136Z` |
| `evaluation/artifacts/exp-initial-comparison/comparison.json` | `comparison-20260829T123158Z` |

- `case_lists_identical`: **true** (001–012)
- `git_commit` in all three files: `54c0a145b55808e8f68474f0485c80cb430dbcd3`
- Python **3.12.10**; pins as recorded in the JSON `configuration` objects
- Holdout was **not** passed into the graph (`holdout_passed_to_graph`: false)

## Baseline result

From `evaluation/artifacts/exp-initial-comparison/baseline.json`:

- `n_cases` 12; `n_cases_completed` 11; `n_cases_failed` **1**
- Official aggregate **WIS: null** (failed cases are kept in the mean)
- `human_intervention_count`: 0
- `runtime.wall_seconds`: 22.94
- Selection: expanding-window backtest WIS, then fallback order
  naive → seasonal_naive → ets → arima

## New result

From `evaluation/artifacts/exp-initial-comparison/agent.json`:

- `n_cases` 12; `n_cases_completed` 11; `n_cases_failed` **1**
- Official aggregate **WIS: null**
- `human_intervention_count`: **11** (every completed case
  `review_required` / `human_checkpoint_status` = `waiting_for_approval`)
- `runtime.wall_seconds`: 16.05
- Selection recorded as `orchestrator_backtest_wis_then_verify`

`wis_completed_only` exists in both JSONs. It is **not** the official
primary. For the record only: baseline 0.964, agent 1.203 (higher / worse
WIS on completed cases). Do not cite those as the product win/loss.

## Improvement

**Official headline:** `comparison.json` `aggregate.metrics.wis.relative_improvement`
is **null**. There is **no** measured official WIS improvement.

`n_cases_failed` relative_improvement is **0** (1 vs 1).

Wall-clock `aggregate.wall_seconds.relative_improvement` is **0.30** (agent
wall 16.05s vs baseline 22.94s). That is a **runtime** secondary, not a
forecast-quality win.

### 1. Where advanced beats baseline

**Holdout WIS:** nowhere. Of 11 completed cases, WIS `relative_improvement`
is **0** on eight cases and **negative** on three. No case has WIS
`relative_improvement` > 0.

Secondaries on specific cases (still not the official WIS claim):

- **003** interval **coverage** relative_improvement **+0.625** (0.57 → 0.93),
  with much **worse** WIS and much **wider** intervals
- **009** sMAPE / WMAPE / MASE relative_improvement **+0.50 / +0.25 / +0.25**,
  with **worse** WIS and **wider** intervals
- **010** interval **coverage** relative_improvement **+0.40** (0.71 → 1.0),
  with **worse** WIS and **wider** intervals
- Several cases are **faster** on the agent (e.g. 002, 004, 009)

Tied WIS (same selected family / same holdout numbers): **001, 002, 004,
006, 007, 008, 011, 012**.

### 2. Where advanced loses

Primary (WIS), completed cases:

| case | challenge | baseline model | agent model | WIS rel. improvement |
|---|---|---|---|---|
| **003** | trend + seasonality | seasonal_naive | naive | **−5.15** |
| **009** | intermittent demand | seasonal_naive | naive | **−0.55** |
| **010** | short history | seasonal_naive | naive | **−0.18** |

All three are **strategy mismatches**: baseline kept `seasonal_naive` from a
full four-model backtest; the agent emitted `naive`.

### 3. Largest failure modes

1. **Case 005 (missing values)** — both systems `failed`,
   `ForecastInterfaceError`, non-finite training values, no impute/drop.
   This **zeros official aggregate WIS** on both sides. Messages:
   comparison `errors`.
2. **Verifier-driven retry away from the backtest winner (003)** — agent
   `retry_number` = 1. Stored backtest still ranks `seasonal_naive` first
   (official WIS 0.50) over `naive` (2.28), but the **selected** model is
   `naive`. Holdout WIS 0.44 → 2.68. Matches orchestrator behavior: a
   verification **FAIL** retries the next strategy (`_next_strategy`), then
   this run finished **WARN** + checkpoint.
3. **Restricted candidate set (009, 010)** — agent `backtest` snapshots
   list **only naive**. Baseline compared four models and chose
   `seasonal_naive`. Point accuracy mixed on 009; **WIS still worse**.
4. **WARN + human gate on every completed case** — final
   `verification_overall` is **WARN** for all 11 completions. Checkpoints
   fire on WARN (`low_forecast_confidence` and `material_uncertainty`).
   Catalog eval does **not** call Accept, so `human_intervention_count` is
   11 vs 0.

ETS/ARIMA backtest folds often fail on both systems (recorded as
`n_folds_failed` in snapshots). That is shared, not an agent-only defect.

### 4. Most expensive workflow steps

Eval JSON has **per-case wall time**, not per-node (PROFILE / STRATEGY /
VERIFY) timings. `persist_trajectory` is false on this harness, so there is
no trajectory cost breakdown.

Slowest **cases** (`runtime_seconds`):

| rank | baseline | agent |
|---|---|---|
| 1 | 001 3.30s | **011** 4.09s (long horizon) |
| 2 | 012 3.10s | 003 2.35s |
| 3 | 011 2.75s | 001 2.25s |

Fastest completed agent cases: 010 (0.17s), 004 (0.18s), 009 (0.27s).

Failed **005** is cheap (~0.15–0.17s) because fit aborts early.

`cost` is **null** in both aggregates (no LLM billing).

### 5. Verification failures

Recorded **final** `verification_overall` (agent JSON):

- **FAIL** as the stored overall: **0** cases
- **WARN**: **11** completed cases
- **PASS**: **0** cases
- **null**: **005** (failed before a stored overall)

003’s `retry_number` = 1 is the artifact evidence that a **FAIL** occurred
**during** the run and was retried; the **final** overall is still WARN.

Per-check FAIL/WARN names are **not** in `evaluation/results/*.json`. Do not
invent which deterministic check fired.

### 6. Retry frequency

| | Value |
|---|---|
| Cases with `retry_number` ≥ 1 | **1 / 12** (003 only) |
| Completed cases with a retry | **1 / 11** |
| `retry_number` on 003 | **1** |
| All other cases | **0** |

Retries are bounded in code; this run did not exhaust the cap (no
`verification_failed_repeatedly` on the stored checkpoint status — all
waiting cases are WARN-driven, not retry-exhaustion).

### 7. Cases needing improvement

Priority from this pair (not a commitment to silent imputation):

1. **005** — explicit missing-value **policy** (named, logged) or accept a
   standing catalog failure and keep official WIS null
2. **003** — retry must not replace a better backtest winner with a worse
   holdout model without an evidence-backed rule
3. **009, 010** — candidate proposal vs always-compare-four (baseline)
4. **All completed agent cases** — WARN/checkpoint so the eval path never
   “accepts”; either eval-only auto-note or fewer false WARN gates
5. **011** — slowest agent case; long horizon stress

## Failure cases

Both systems, **005**, `ForecastInterfaceError` (see `comparison.json`
`errors`). No case was dropped from `case_list`.

Holdout quality losses: **003, 009, 010** as in the WIS table above.

## Decision

**Do not claim an official WIS win.** Headline improvement is undefined
while 005 fails on both sides.

**Keep** the shared catalog, the baseline harness, and the orchestrator as
the advanced path. **Do not** change models or silently fill missing values
to manufacture a WIS number.

Next measured experiment should pick **one** of: missing-value policy;
retry/selection alignment with backtest WIS; candidate-set vs full
comparison — then re-run the same three commands.

## Lesson learned

Advanced control flow (verify, retry, propose-candidates, human WARN gate)
can **match** the baseline when the same model is selected, and can
**hurt** WIS when it selects `naive` instead of `seasonal_naive`. Runtime
and some interval-coverage secondaries moved in the agent’s favor; they
are not a substitute for official WIS. Human-intervention count is a real
cost of the checkpoint design on this catalog.
