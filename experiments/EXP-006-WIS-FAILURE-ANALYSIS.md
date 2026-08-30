# EXP-006 WIS failure analysis

- **Kind:** diagnosis (no code change)
- **Status:** analysis only
- **Date:** 2026-08-29
- **Decision:** not an implementation experiment

This file is **root-cause analysis**. It is not the EXP-006 missing-value
policy (`experiments/EXP-006-missing-policy.md`). Application code, evaluation
cases, and the primary metric were not changed for this write-up.

**Official pair (source of truth):**

| File | Id |
|---|---|
| `evaluation/results/baseline.json` | `baseline-20260829T125209Z` |
| `evaluation/results/agent.json` | `agent-20260829T125231Z` |
| `evaluation/results/comparison.json` | `comparison-20260829T125254Z` |

`git_commit`: `54c0a145b55808e8f68474f0485c80cb430dbcd3`. Copied from
`evaluation/artifacts/EXP-008-full-candidates/` (see changelog).
`case_lists_identical`: true. Catalog cases `001`–`012`. `n_cases_failed`: 0 / 0.

## Headline finding

On this official pair the advanced solution **does not lose to baseline on
WIS**. Every case is a **tie**. Aggregate WIS is identical.

The hackathon bar (“advanced beats baseline on WIS”) fails because the agent
path is **numerically isomorphic** to the baseline selector: same four models,
same official backtest-WIS ranking, same fitters (`run_baseline_forecast`),
same `score_holdout`. Agents add process (WARN/FAIL, human checkpoints, extra
wall time), not different `yhat` / intervals.

Historical **losses** (EXP-006/007) were real and are already closed. They are
not the current official result.

---

## A. CURRENT RESULTS

Primary metric: official mean WIS over the **full** 12-case list (failures not
dropped). Direction: lower is better.

| Quantity | Value |
|---|---|
| Baseline aggregate WIS | `0.9153325914744158` |
| Advanced (agent) aggregate WIS | `0.9153325914744158` |
| Absolute difference (agent − baseline) | `0.0` |
| Percentage difference vs baseline | `0.0%` |
| `relative_improvement` (comparison JSON) | `0.0` |

Positive `relative_improvement` would mean the agent is better. **0.0 is
parity, not a win.**

Other official aggregates (also tied): sMAPE `9.02472`, WMAPE `15.19898`,
MASE `1.05935`, interval coverage `0.89881`, interval width `21.28537`.

Process metrics (not WIS):

| Metric | Baseline | Agent |
|---|---|---|
| Human interventions | 0 | **12** (every case `waiting_for_approval`) |
| Wall seconds | 16.85 | 19.59 (`relative_improvement` **−0.1624**) |

Eval harness: `persist_trajectory=False` on catalog runs. Checked-in
trajectories under `backend/tests/fixtures/trajectories/` are schema
examples, not this evaluation’s agent+human traces.

---

## B. PER-CASE ANALYSIS

Winner on WIS: **tie** on every case. Selected model is identical on both
systems. `retry_number` is **0** everywhere. `review_required` is **true** on
the agent for all 12 (checkpoint status `waiting_for_approval`). The eval
harness still **scores** the waiting forecast; it does not wait for a human
Accept that would change numbers.

Holdout WIS, coverage, and width are the same on both sides (identical
forecasts). “Important warnings” combine agent `verification_overall` with
holdout interval diagnostics and backtest ranking gaps.

| Case | Baseline WIS | Advanced WIS | Winner | Diff (A−B) | Selected model | Retries | Verification | Important warnings |
|---|---|---|---|---|---|---|---|---|
| 001 | 0.454943 | 0.454943 | tie | 0 | naive | 0 | WARN | Coverage **0.571** vs nominal 0.95; width 2.09; ETS/ARIMA `official_wis` null (1 fold failed); completed-only ARIMA WIS **0.053** vs naive official **0.373** |
| 002 | 0.132345 | 0.132345 | tie | 0 | seasonal_naive | 0 | WARN | Coverage 1.0; width 2.40; ETS/ARIMA unranked; completed-only ARIMA **0.119** vs SN official **0.254** |
| 003 | 0.435545 | 0.435545 | tie | 0 | seasonal_naive | 0 | **FAIL** | Coverage **0.571**; width 2.17; no retry (rank-1 already best official WIS); ETS/ARIMA unranked; completed-only ARIMA **0.138** vs SN **0.500** |
| 004 | 4.046263 | 4.046263 | tie | 0 | naive | 0 | WARN | Noisy series; coverage 1.0 but width **93.1** (WIS dominated by interval width); MAE 7.48; ETS/ARIMA unranked |
| 005 | 0.378888 | 0.378888 | tie | 0 | seasonal_naive | 0 | WARN | Missing-values case; train-only interpolate; coverage 0.929; width 3.97 |
| 006 | 1.373060 | 1.373060 | tie | 0 | naive | 0 | WARN | Outliers; coverage 1.0; width **75.1**; MAE **0.36** (point error small, intervals huge) |
| 007 | 0.308848 | 0.308848 | tie | 0 | naive | 0 | WARN | Structural-break case; coverage 1.0; width 12.9; detective can flag breaks but no named train-window transform is applied |
| 008 | 0.338903 | 0.338903 | tie | 0 | seasonal_naive | 0 | WARN | Event/context case; context labels recorded, **not** used to change the forecast; coverage 1.0; width 14.0 |
| 009 | 0.418546 | 0.418546 | tie | 0 | seasonal_naive | 0 | WARN | Intermittent demand; sMAPE **57.1** while WIS remains moderate; coverage 1.0; width 13.7 |
| 010 | 0.892381 | 0.892381 | tie | 0 | seasonal_naive | 0 | WARN | Short history (`n_train=16`, horizon 7); coverage **0.714**; ETS/ARIMA **2** folds failed and `wis_completed_only` is also null |
| 011 | 0.826216 | 0.826216 | tie | 0 | seasonal_naive | 0 | WARN | Long horizon 90; coverage 1.0; width 8.50; completed-only ARIMA **0.228** vs SN official **1.032** |
| 012 | 1.378054 | 1.378054 | tie | 0 | seasonal_naive | 0 | WARN | Adversarial regime change; coverage 1.0; width 23.5; completed-only ETS **1.251** vs SN official **1.529** |

Case 004 alone is **~37%** of the official mean (4.046 / 12 ≈ 0.337 of 0.915).
Ties on 004 therefore dominate the headline number.

Eval JSON does **not** store per-check verifier IDs. Catalog eval does **not**
pass holdout actuals into the graph (`holdout_passed_to_graph: false`), so
**V06 (interval coverage) is N/A** during verification and cannot explain 003
FAIL. 003 FAIL is consistent with **V03** (trend vs near-flat/opposite
seasonal-naive slope) and/or **V04** (seasonal pattern vs last cycle) on a
trend+seasonality series. That FAIL did not change the model (EXP-007).

---

## C. FAILURE CLASSIFICATION

### Current official pair

**No case has winner = baseline or winner = advanced on WIS.** Classifying
“where advanced loses” on this pair would be false.

The **catalog-level failure** is: advanced does not **beat** baseline.

| Category | Applies now? | Evidence |
|---|---|---|
| Evaluation implementation issue | **No** (for WIS inequality) | Same `score_holdout` → `app.forecasting.metrics.wis`; identical `case_list`; same split and train missing policy |
| Model selection failure (agent vs baseline) | **No** on current pair | Same `selected_model_id` and `selection_rule=official_backtest_wis` on all 12 |
| Model selection **ceiling** (shared) | **Yes** | ETS/ARIMA never ranked; completed-only WIS often much lower |
| Retry strategy failure | **No** on current pair | `retry_number=0`; EXP-007 prevents worse-WIS swap on 003 FAIL |
| Verification failure (as WIS driver) | **No** | 003 FAIL did not change yhat; 11 WARN cases match baseline numbers |
| Prediction interval failure (shared) | **Partial** | 001/003 coverage 0.57; 004/006 extreme width; **same on both systems** |
| Point forecast failure (shared) | **Partial** | 004 MAE 7.48; 009 sMAPE 57; **same on both** |
| Anomaly handling failure (agent-only) | **No WIS gap** | 006 still naive like baseline; detective does not apply a clip/transform |
| Structural break failure (agent-only) | **No WIS gap** | 007/012 match baseline; no post-break train window |
| Seasonality failure (agent-only) | **No WIS gap** | Seasonal cases already pick `seasonal_naive` when it wins official WIS |
| Horizon mismatch | **No** | Explicit `forecast_horizon` on artifacts; scored length matches holdout |
| Insufficient history | **Shared constraint** | 010: ETS/ARIMA cannot complete any official WIS; both pick SN |
| Other: **numerical isomorphism** | **Yes — primary** | Agent backtest allow-list = `BASELINE_MODEL_IDS`; same ranking rule; same fit |

### Historical losses (not current official WIS)

These explain the audit’s “does not beat baseline” **history**, already
mitigated:

| When | Cases | Category | What happened |
|---|---|---|---|
| EXP-006 pair | 003 | Retry strategy failure | VERIFY FAIL swapped rank-1 `seasonal_naive` → `naive`; holdout WIS **−5.15** vs baseline |
| EXP-006/007 pairs | 009, 010 | Model selection failure | STRATEGY shortlist executed as the backtest set; often only `naive`; baseline saw all four |
| Frozen control `exp-initial-comparison` | 005 | Missing values / eval completeness | Official aggregate WIS **null** (`ForecastInterfaceError` on NaNs); both failed |

EXP-007 closed 003. EXP-008 closed 009/010. Result: **parity**, not a win.

---

## D. WIS IMPLEMENTATION AUDIT

Implementation: `backend/app/forecasting/metrics.py` `wis()`. Evaluation
invokes it via `evaluation/metrics.py` `score_holdout` — **no forked formula**.
Backtests call the same `wis()` per fold (`backend/app/forecasting/backtesting.py`).

### Formula (point + interval)

Bracher-style WIS for **K = 1** central interval plus a median. `yhat` is the
median `m`. `α = 1 − coverage` with catalog `coverage = 0.95` so `α = 0.05`.

```text
IS_α = (u − l) + (2/α)(l − y)_+ + (2/α)(y − u)_+
WIS_t = 1/(K + 0.5) * ( 0.5 |y − m| + (α/2) IS_α )
reported WIS = mean_t(WIS_t)
```

`1/(K+0.5) = 2/3`. This is **not** MAPE. Interval score and absolute error are
mixed by construction (primary metric), while sMAPE/MAE and coverage/width are
also stored separately (secondaries).

### Checks requested

| Topic | Finding |
|---|---|
| Point forecast component | `0.5 |y − yhat|` inside the WIS average. Same `yhat` on both systems. |
| Prediction interval component | Gneiting–Raftery `IS_α` on `[lower, upper]`. Same bounds on both systems. |
| Coverage | Secondary `interval_coverage`; **not** a substitute for WIS. Nominal 0.95. Empirical holdout coverage is **below** 0.95 on 001, 003, 010. |
| Interval width | Secondary mean `(upper − lower)`. Extreme on 004/006; enters WIS via `IS_α`. |
| Quantile / interval assumptions | **One** central 95% interval + median. Not a full quantile fan. Models use Gaussian `z` × residual σ × √h (naive/ETS/ARIMA) or seasonal-naive repeat factor (`_support.py`). Not conformal. |
| Scaling | Constant `2/3` and `α/2` on `IS_α`. No per-case rescaling of WIS. MASE uses in-sample seasonal naive; WIS does not. |
| Aggregation | Official catalog mean: `evaluation/metrics.py` `official_mean` — any missing case → official mean **None**. Current pair: all 12 finite. Per-horizon: **unweighted mean** of step-wise WIS (no discounting of far steps). |
| Missing values | Metrics omit NaN **pairwise** (never filled). Case 005: train interpolated **after** split; holdout not filled. Source CSV unchanged. |
| Horizon aggregation | Mean over the holdout vector length (`forecast_horizon` steps). 011 (h=90) and 012 (h=28) are not down-weighted in the 12-case mean. |

### Baseline vs advanced: identical evaluation?

**Yes, for scoring.**

- Same catalog CSVs, `history_length`, `forecast_horizon`, seeds.
- Same `split_train_holdout` then `apply_linear_interpolate_train` on train only.
- Holdout **not** passed into the orchestrator.
- Same `COVERAGE = 0.95`.
- Same `score_holdout` / `wis()`.

Do **not** change this metric because the agent ties. A WIS rewrite would not
create a legitimate win.

---

## E. MODEL SELECTION AUDIT

### What baseline uses

`BASELINE_MODEL_IDS` = `naive`, `seasonal_naive`, `ets`, `arima`
(`app/services/forecast_service.py`).

Harness: expanding-origin backtest on **train only**, `target_backtest_folds=5`,
rank by **official** fold-mean WIS (`evaluation/run_baseline.py`
`select_model_id`). Fallback order if nothing ranks: naive → seasonal_naive →
ets → arima. A **completed-only** fallback exists **only if no model has
official WIS**. On every current case, naive and/or seasonal_naive **do** have
official WIS, so ETS/ARIMA completed-only scores are **ignored**.

### What advanced evaluates

After EXP-008, BACKTEST executes the **full allow-list** (same four ids).
STRATEGY `propose_candidate_ids` is a **hypothesis** (typically `naive`, plus
`seasonal_naive`/`ets` if seasonality, plus `ets`/`arima` if trend). It no
longer restricts which models are backtested.

Selection: rank 1 by official backtest WIS (`ForecastStrategistReport`,
`selection_rule=official_backtest_wis`). VERIFY FAIL retries only if an untried
model has **strictly lower** official backtest WIS (EXP-007). Rank-1 is already
best among **ranked** models, so retry almost never fires (`retry_number=0`).

### Is selection based on backtest evidence?

**Yes**, for the two models that finish every planned fold. **No** for ETS and
ARIMA: `aggregate.wis` is `None` if **any** planned fold failed
(`BacktestAggregate`). They receive `rank=None` and cannot win.

Cause of typical **1 failed fold** (daily `period=7`):

- ETS seasonal: needs `≥ 2 * period` observations (`ets.py`).
- Seasonal ARIMA: needs `≥ 2 * period + 8` (`arima.py`).
- Shared expanding plan uses a small `min_train_size` (order 8), so **fold 0**
  is too short. Later folds often succeed → `wis_completed_only` exists, official
  WIS does not.

Case 010: `n_train=16`; ETS/ARIMA **2** folds failed; completed-only also null.

### Is the selected model the lowest-WIS model?

It is the lowest-**official**-WIS model among models with a finite official
mean. It is **not** always the lowest `wis_completed_only` model.

Examples (agent/baseline backtest snapshots, identical):

| Case | Rank-1 official | Completed-only better (unranked) |
|---|---|---|
| 001 | naive 0.373 | ARIMA 0.053, ETS 0.073 |
| 003 | seasonal_naive 0.500 | ARIMA 0.138, ETS 0.173 |
| 011 | seasonal_naive 1.032 | ARIMA 0.228, ETS 0.492 |
| 006 | naive 2.046 | ARIMA completed 2.070 (**not** better) |
| 008 | seasonal_naive 1.164 | ETS/ARIMA completed **worse** |

### Does the selection objective match final evaluation?

**Same formula, different sample.** Selection WIS = rolling-origin **train**
folds. Final WIS = **holdout** after last train origin. Holdout is not used for
selection (correct; no leakage). The mismatch is **window**, not a different
metric implementation.

If ETS/ARIMA became eligible under the **same** official-WIS rule in **shared**
backtesting, **both** harnesses would likely pick them and **still tie**.
Beating baseline requires an **agent-only** difference or a frozen baseline
while the agent changes.

---

## F. PREDICTION INTERVAL AUDIT

WIS penalizes both `|y − ŷ|` and interval **width** plus **misses** (`2/α`
with `α=0.05` is a large miss penalty).

Catalog eval **cannot** calibrate on holdout coverage: V06 is N/A without
actuals. Holdout coverage below is **scored after** the graph, identically for
both systems.

| Case | Coverage | Width | WIS | MAE (point) | Interval vs point |
|---|---|---|---|---|---|
| 001 | 0.571 | 2.09 | 0.455 | 1.06 | **Undercoverage**; modest width; naive √h intervals too tight for trend error growth |
| 002 | 1.000 | 2.40 | 0.132 | 0.28 | Well covered; WIS small |
| 003 | 0.571 | 2.17 | 0.436 | 0.96 | Same undercoverage pattern as 001 on a seasonal-naive point forecast |
| 004 | 1.000 | 93.1 | **4.05** | 7.48 | Coverage OK; **width dominates WIS**; point error also large (noise) |
| 005 | 0.929 | 3.97 | 0.379 | 0.90 | Near nominal |
| 006 | 1.000 | 75.1 | 1.37 | **0.36** | Point forecast relatively good; **intervals inflated** by outlier-driven σ |
| 007 | 1.000 | 12.9 | 0.309 | 0.28 | Wide but coverage 1.0 |
| 008 | 1.000 | 14.0 | 0.339 | 0.32 | Same pattern |
| 009 | 1.000 | 13.7 | 0.419 | 0.57 | Point sMAPE terrible (zeros); WIS still moderate because of interval score mix |
| 010 | 0.714 | 4.03 | 0.892 | 1.87 | Short series; coverage gap |
| 011 | 1.000 | 8.50 | 0.826 | 2.05 | Long horizon; coverage 1.0 (possibly conservative) |
| 012 | 1.000 | 23.5 | 1.38 | 2.96 | Regime change; wide intervals |

**Conclusion:** several cases have **poor intervals even when points look
acceptable** (006) or **poor coverage with moderate width** (001, 003). That
hurts WIS for **both** systems. Fixing intervals in shared `_support.py` would
move both scores together unless the agent applies a **different** interval
policy.

---

## G. AGENT VALUE AUDIT

Catalog evaluation uses the orchestrator **without a live LLM** (deterministic
nodes + tools). `human_intervention_count=12` does not change scored forecasts.

| Agent / node | Decision | Tool(s) | Measurable outcome it can influence | Improves any eval case vs baseline? | Hurts any eval case vs baseline? |
|---|---|---|---|---|---|
| Data detective | Diagnostics, forecastability, **proposed** transforms (not applied) | `inspect_series`, `diagnose_*` data tools | Could enable named train transforms; currently **does not change yhat** | **No** (WIS tie) | **No** |
| Context analyst | Record event/context **facts**; no causality | `inspect_context` | Could inform regime/event handling; **does not adjust forecasts** (module contract) | **No** (008 still matches baseline) | **No** |
| Forecast strategist | Hypothesis shortlist; ranking from backtest | Backtest comparison / ranking | **Does** choose `strategy_id` from official WIS | **No incremental WIS** vs baseline after EXP-008 (same choice) | Historically 009/010 (EXP-007 pair); **not now** |
| Orchestrator BACKTEST | Executes allow-list | `run_forecast_strategist` / rolling backtest | Same candidate set as baseline | Closed 009/010 **losses**; did not create wins | **No** on current pair |
| Forecast fit | Fit selected id | `forecast_fit` / `run_baseline_forecast` | yhat, intervals | Same models as baseline | **No** |
| Verifier | PASS/WARN/FAIL challenge | `verify_forecast` (V01–V09) | Retry or checkpoint; **does not emit numbers** | **No** WIS win; 003 FAIL did not switch model | Historically 003 (EXP-006); **not now** |
| Retry policy | Swap only if better official WIS | — | Prevents worse models | Recovered 003 to **tie** | Blocks using unranked ETS/ARIMA (no official WIS to compare) |
| Analyst | Evidence-cited narrative | Reads forecast/verify evidence | None on WIS | **No** | **No** |
| Human checkpoint | Explicit gate; eval does not Accept | — | `review_required`; 12 interventions | **No** effect on scored WIS | Extra process cost only |

**Net:** agents currently cause **no measurable WIS improvement** over
baseline. They also cause **no WIS harm** on the official pair. Value is
decision-support (warnings, FAIL on 003, checkpoints), not forecast accuracy.

---

## H. TOP 5 ROOT CAUSES

Ranked by how much they explain **failure to beat baseline on WIS** (not
“agent worse than baseline”).

### 1. Numerical isomorphism with the baseline selector

- **Evidence:** Identical `selected_model_id`, holdout WIS, coverage, width on
  all 12 cases; EXP-008 made backtest sets equal; both use `official_backtest_wis`.
- **Affected cases:** 001–012.
- **Severity:** **Critical** for the hackathon bar.
- **Proposed fix:** An **agent-only** numerical policy (eligibility of ETS/ARIMA,
  named transform, or interval policy) while baseline stays the current selector.
- **Expected impact:** Necessary condition for `relative_improvement > 0`.
- **Validate:** Isolated `evaluation/artifacts/EXP-009-…` vs this official pair;
  require `case_lists_identical` and no dropped cases.

### 2. ETS/ARIMA ineligible for official backtest WIS (shared ceiling)

- **Evidence:** Every case: ETS and ARIMA `official_wis=null`, `rank=null`,
  typically `n_folds_failed=1` (010: 2). Completed-only WIS often far below
  rank-1 (001 ARIMA 0.053 vs naive 0.373). Fitters refuse short first folds
  (`ETS seasonal needs at least 2*period`; SARIMA `2*period+8`).
- **Affected cases:** All 12 for eligibility; largest **potential** holdout
  gaps if completed-only predicted holdout: **001, 002, 003, 005, 009, 011,
  012**. 006/008 completed-only does **not** favor the unranked models.
- **Severity:** **High** (blocks the only unused models in the allow-list).
- **Proposed fix:** Agent-only fold **planning** with model-specific
  `min_train_size` so ETS/ARIMA planned folds are all completable → finite
  **official** WIS (failed folds never planned). Prefer this over silently
  ranking on `wis_completed_only` (that statistic is labeled non-headline).
- **Expected impact:** Agent may select ETS/ARIMA on trend/seasonal cases;
  001/011 are the largest backtest gaps. Shared min_train change would likely
  **tie again**.
- **Validate:** Same 12-case compare; inspect per-case `selected_model_id`
  and holdout WIS; keep failed-fold poisoning for any fold that still fails.

### 3. Shared residual-σ intervals are miscalibrated for WIS

- **Evidence:** 001/003 empirical coverage 0.57 vs 0.95; 004/006 coverage 1.0
  with widths 93 and 75. Naive uses first-difference σ × √h; outliers inflate
  σ (006). Verifier never sees holdout coverage in eval.
- **Affected cases:** 001, 003 (undercoverage); 004, 006 (width); 010 (0.71).
- **Severity:** **High** for absolute WIS; **medium** for beating baseline
  unless the agent uses a **different** interval method.
- **Proposed fix:** Agent-only: backtest-calibrated interval inflation/deflation
  or last-window σ after detective outlier/break flags. Do not retune WIS.
- **Expected impact:** Could cut 004’s 4.05 contribution if width shrinks
  without collapsing coverage; 001/003 if undercoverage penalties fall.
- **Validate:** Report coverage, width, WIS, MAE together; success only if
  **official WIS** improves vs this baseline pair.

### 4. Diagnostics never become named numerical transforms

- **Evidence:** Context analyst “does not adjust forecasts.” Detective
  proposes transforms; source data unmodified; eval applies only shared
  `linear_interpolate_train`. 007/008/012 match baseline models.
- **Affected cases:** 006 (outliers), 007 (break), 008 (events), 012 (regime).
- **Severity:** **Medium** (agent unique value unused).
- **Proposed fix:** One explicit, logged transform (e.g. fit on post-break
  window) applied by deterministic code after detective evidence, agent path
  only.
- **Expected impact:** Possible WIS gain on 007/012; risk of harm if the break
  screen is wrong.
- **Validate:** Per-case WIS on 007/012 plus full-catalog official mean.

### 5. Verification and checkpoints do not optimize WIS

- **Evidence:** 003 FAIL, retry_number 0, same WIS as baseline. WARN on 11
  cases → 12 human gates; scored output unchanged. Retry cannot consider
  unranked ETS/ARIMA (`_official_wis_for` is null).
- **Affected cases:** All 12 (process); 003 (FAIL without alternative).
- **Severity:** **Medium** for “agentic improvement”; **low** for current WIS
  **harm**.
- **Proposed fix:** After FAIL/WARN, consider models with finite completed-only
  WIS only inside a **named experiment**, or skip unverifiable V06 in eval and
  instead use backtest fold coverage as the interval challenge. Do not auto-approve.
- **Expected impact:** Unlocks cause 2 during FAIL; checkpoints remain honest.
- **Validate:** Trajectory + comparison JSON; no unbounded retries.

---

## I. RECOMMENDED EXPERIMENTS

Maximum **three**. No UI. No extra agents (no evidence an additional agent is
required). Primary metric stays WIS. Cases stay. No hard-coded scores.

### Experiment 1 (implement first) — Agent-only model-specific backtest origins

**Hypothesis:** If the agent plans ETS/ARIMA expanding folds with
`min_train_size` high enough that **every planned fold can fit**, those models
get finite **official** backtest WIS and will be selected when they beat naive /
seasonal_naive. Holdout WIS will then drop on trend/long-horizon cases (001,
011) enough to pull the 12-case mean below baseline. Baseline keeps the current
shared short first fold (ETS/ARIMA remain unranked).

**Implementation change:** Agent backtest path only: per-model minimum train
length (ETS: `2 * period`, ARIMA: `2 * period + 8` when seasonal). Do not drop
failed folds from official means if a fold still fails. Do not use holdout for
selection. Do not change `wis()`.

**Expected effect:** Agent `selected_model_id` diverges on some cases; official
aggregate WIS `<` `0.91533`.

**Risk:** Fewer folds → noisier ranking; completed-only gaps may **not**
generalize to holdout; 004/006 might pick a worse holdout model; isomorphism
returns if the same planner is later copied into baseline.

**Evaluation command:**

```powershell
python evaluation/run_baseline.py --output-json evaluation/artifacts/EXP-009-ets-arima-min-train/baseline.json --output-md evaluation/artifacts/EXP-009-ets-arima-min-train/baseline.md
python evaluation/run_agent.py --output-json evaluation/artifacts/EXP-009-ets-arima-min-train/agent.json --output-md evaluation/artifacts/EXP-009-ets-arima-min-train/agent.md
python evaluation/compare.py --baseline evaluation/artifacts/EXP-009-ets-arima-min-train/baseline.json --agent evaluation/artifacts/EXP-009-ets-arima-min-train/agent.json --output-json evaluation/artifacts/EXP-009-ets-arima-min-train/comparison.json
```

**Success criterion:** `aggregate.metrics.wis.relative_improvement` **> 0** on
the full 12-case list; `n_cases_failed` remains 0; no case dropped; baseline
JSON on this isolated pair still matches current official WIS
(`0.9153325914744158`) so the comparison is against the same selector.

### Experiment 2 — Agent-only last-regime train window after a detected break

**Hypothesis:** Detective-detected structural breaks (007, 012) make full-history
naive/seasonal_naive suboptimal. Fitting the **already selected** family on a
logged post-break window (deterministic copy, not in-place CSV edit) reduces
holdout WIS on those cases without changing 001–006.

**Implementation change:** Named transform applied only on the agent path when
break evidence is present; baseline unchanged.

**Expected effect:** WIS down on 007 and/or 012; modest catalog-mean move
(those cases are 0.31 and 1.38).

**Risk:** False break detection shortens train too much (especially 010-like
lengths); may **raise** WIS. 012 is adversarial.

**Evaluation command:** same three-script pattern under
`evaluation/artifacts/EXP-010-post-break-window/`.

**Success criterion:** Official 12-case WIS `relative_improvement > 0` **or**,
if catalog mean is flat, **both** 007 and 012 agent WIS strictly below this
pair’s values with no other case worse — still not a headline win unless the
mean improves. Headline success remains **catalog official WIS**.

### Experiment 3 — Agent-only interval calibration from backtest residuals

**Hypothesis:** 001/003 WIS is inflated by undercoverage penalties; 004/006 by
width. Using backtest-fold empirical coverage to scale residual σ **after**
model selection (agent only) improves WIS while point forecasts stay the same.

**Implementation change:** Deterministic interval restretch in the agent fit
node; cite backtest coverage evidence; do not invent yhat.

**Expected effect:** Coverage closer to 0.95 on 001/003; narrower 004/006 if
outliers dominate σ; WIS down if the IS_α tradeoff is favorable.

**Risk:** Wider intervals increase the width term; WIS can **worsen**. Scaling
on train folds may not match holdout. Easy to accidentally share the change
with baseline.

**Evaluation command:** `evaluation/artifacts/EXP-011-interval-scale/` with the
same three scripts.

**Success criterion:** Official WIS `relative_improvement > 0`; report
coverage/width/MAE so a coverage-only “win” is not mistaken for WIS.

---

## Recommendation: implement Experiment 1 first

The official pair is a **WIS tie**, not an agent loss. The largest unused,
evidence-backed signal is **ETS/ARIMA never receiving official backtest WIS**
while their completed folds look much better on 001, 003, and 011. Experiment 1
makes those models **selectable under the same official-WIS rule** without
dropping failed folds, without touching the metric, and without adding agents.
That is the highest-leverage path to a **measured** `relative_improvement > 0`
against the current baseline selector.
)
