# EXP-010 promotion

Controlled promotion of EXP-010 to the official advanced solution.
Not a new optimization experiment. `R` was not retuned. EXP-011 was not started.

## 1. Previous default

Official advanced path was **EXP-008 shared-origin parity**:
`selection_policy=default`, `origin_planning=shared`.

Archived (not deleted) at `evaluation/artifacts/pre-exp010-promotion/`:

| File | Previous official id |
|---|---|
| `baseline.json` | `baseline-20260829T125209Z` |
| `agent.json` | `agent-20260829T125231Z` |
| `comparison.json` | `comparison-20260829T125254Z` |

WIS both sides: **0.9153325914744158**. `relative_improvement` **0.0**.
Working-tree commit at archive time: `524837b0ea8a9378f7d9d6601d080eceff602431`.

## 2. Promoted configuration

| Setting | Value |
|---|---|
| `selection_policy` | `exp010` (Python / CLI default) |
| Origin planning | `model_specific` (forced by exp010) |
| Veto | last/earlier fold WIS ≥ `EXP010_LAST_TO_EARLIER_VETO` (`5.0`) |
| Ranking | official backtest WIS among models that pass |
| Baseline | unchanged `run_rolling_origin_backtest` |
| WIS / cases / holdout / horizon | unchanged |

Official command (no experimental flag):

```powershell
python evaluation/run_baseline.py
python evaluation/run_agent.py
python evaluation/compare.py
```

Historical EXP-009 (planner only, no veto):

```powershell
python evaluation/run_agent.py --origin-planning model_specific
```

Frozen EXP-010 isolate (same policy as official; do not overwrite):
`evaluation/artifacts/EXP-010-robust-model-selection/`.

## 3. Baseline result

| Field | Value |
|---|---|
| `evaluation_run_id` | `baseline-20260830T020244Z` |
| Official WIS | **0.9153325914744158** |
| `n_cases_failed` | 0 |
| Cases | 001–012 |

Matches the previous official baseline WIS exactly.

## 4. EXP-010 / official advanced result

| Field | Value |
|---|---|
| `evaluation_run_id` | `agent-20260830T020331Z` |
| `comparison_id` | `comparison-20260830T020453Z` |
| Official WIS | **0.7939144093884205** |
| `selection_policy` | `exp010` |
| `origin_planning` | `model_specific` |
| `n_cases_failed` | 0 |
| Human interventions | 12 |

## 5. Improvement

`wis.relative_improvement` = **0.13264925035654543** (~**13.26%**).

Holdout outcomes: advanced **8**, baseline **2**, ties **2**.

Do not claim a win on every case.

## 6. Per-case regression validation

Compared `evaluation/results/agent.json` (`agent-20260830T020331Z`) to the
frozen isolate `evaluation/artifacts/EXP-010-robust-model-selection/agent.json`
(`agent-20260830T014147Z`).

For every case, these matched exactly:

- selected model
- per-model official backtest WIS
- last/earlier stability ratio
- veto / selectable / veto_reason
- holdout WIS
- verification_overall
- retry_number

Expected metadata differences only: timestamp, run id, git commit, duration.

`material_diffs` = **0**. No stop condition.

| Case | Selected | Verify | Retry | Holdout WIS | vs baseline |
|---|---|---|---|---|---|
| 001 | arima | WARN | 0 | 0.04813636648437247 | agent |
| 002 | arima | WARN | 0 | 0.09053487187326001 | agent |
| 003 | arima | FAIL | 0 | 0.12509165740310216 | agent |
| 004 | arima | WARN | 0 | 2.455469571202966 | agent |
| 005 | arima | WARN | 0 | 0.16360163677315423 | agent |
| 006 | naive | WARN | 0 | 1.373060300094421 | tie |
| 007 | seasonal_naive | WARN | 0 | 0.37619603503792565 | baseline |
| 008 | arima | WARN | 0 | 0.27447528057327975 | agent |
| 009 | arima | WARN | 0 | 0.3779421029944304 | agent |
| 010 | seasonal_naive | WARN | 0 | 0.8923807354572151 | tie |
| 011 | arima | WARN | 0 | 0.23575021211968247 | agent |
| 012 | naive | WARN | 0 | 3.114334142647237 | baseline |

## 7. Case 012 analysis

This is a reliability result, not a universal win.

| Path | Selected | Holdout WIS |
|---|---|---|
| EXP-009 | ETS | ~22.83 |
| EXP-010 / official | naive | **3.114334142647237** |
| Baseline | seasonal_naive | **1.378053705549347** |

ETS, seasonal naive, and ARIMA were vetoed on training-fold last/earlier
ratios (~17 / 8.70 / 40.61). Naive (ratio ~1.07) was selected.

The veto **substantially reduced** the EXP-009 catastrophe. The official
advanced result is **still worse than baseline** on case 012. That is not
hidden.

## 8. Tests

Backend `pytest` **305 passed**. Frontend `npm run typecheck` **passed**.

Tests were not weakened to force a pass. Two assertions were updated to
match the promoted official artifact:

- dashboard API now compares aggregate WIS `relative_improvement` to the
  committed file (it is 0.1326, not `None`)
- tracked `evaluation/artifacts/` may include named EXP-* / pre-promotion
  archives; scratch dirs still fail

Shared-origin unit coverage now passes `selection_policy="default"`
explicitly.

## 9. Reproducibility validation

- Official path: `python evaluation/run_agent.py` → `selection_policy=exp010`,
  `origin_planning=model_specific`.
- EXP-009: `--origin-planning model_specific` still means planner-only
  (CLI does not apply today's default veto).
- Frozen EXP-010 artifacts were not overwritten.
- Historical EXP-008 official files were copied, not deleted.
- No benchmark CSV, WIS formula, baseline engine, holdout split, or `R`
  change.

## 10. Files changed

- Default wiring: `evaluation/run_agent.py`, `forecast_strategist.py`,
  `orchestrator.py`, `robustness.py` (`DEFAULT_SELECTION_POLICY='exp010'`).
- Official results: `evaluation/results/{baseline,agent,comparison}.{json,md}`.
- Archive: `evaluation/artifacts/pre-exp010-promotion/`.
- Docs: README, evaluation, architecture, agent-design,
  forecasting-methodology, reproduction, changelog, product-requirements,
  demo-script, experiments index + EXP-009/010 notes.
- Tests: harness default assertions; strategist shared-path tests pass
  `selection_policy="default"` explicitly.

Not changed: baseline engine, WIS implementation, case catalog, holdout
splits, horizon, `EXP010_LAST_TO_EARLIER_VETO`, EXP-009/010 isolate
artifacts, benchmark CSVs.

## 11. Rollback procedure

1. Copy `evaluation/artifacts/pre-exp010-promotion/{baseline,agent,comparison}.json`
   (and `.md`) back to `evaluation/results/`.
2. Set `DEFAULT_SELECTION_POLICY = "default"` in
   `backend/app/forecasting/robustness.py`.
3. Restore CLI argparse defaults if needed so `python evaluation/run_agent.py`
   is shared-origin parity.
4. Do not delete EXP-010 isolate artifacts.

Do not retune `R` as a rollback shortcut.
