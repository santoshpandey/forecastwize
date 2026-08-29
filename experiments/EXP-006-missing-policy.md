# EXP-006 Train-only linear interpolate for missing values

- **Kind:** iteration
- **Status:** executed
- **Date:** 2026-08-29
- **Decision:** **Keep**

## Analyze

Control pair (`evaluation/artifacts/exp-initial-comparison/`, also
`evaluation/results/` after EXP-INITIAL-COMPARISON): official aggregate **WIS
is null** because case **005** fails on both baseline and agent
(`ForecastInterfaceError`: non-finite training values). Failed cases stay in
the official mean, so no headline WIS exists until 005 can complete without
silent source-CSV mutation or holdout leakage.

## Hypothesis

A named policy `linear_interpolate_train`, applied **only after**
`split_train_holdout` to the training copy (never to holdout, never in-place
on the source CSV), on **both** harnesses, will let 005 complete. Official
WIS over the full 12-case list will become non-null. Fitters still reject
NaN; the harness fill is explicit and logged in configuration as
`train_missing_policy`.

## Implement

- `backend/app/forecasting/missing_policy.py`: time interpolation on a copy;
  refuse if any non-finite values remain.
- `evaluation/run_baseline.py` and `evaluation/run_agent.py`: apply the policy
  to `train_y` after the split.

## Test

`backend/tests/test_forecasting_missing_policy.py` (no holdout leak, no
mutate, all-NaN fails). Package isolation still forbids FastAPI/LLM in
forecasting.

## Run same benchmark

From the repository root (does **not** overwrite the frozen control under
`evaluation/artifacts/exp-initial-comparison/` or `evaluation/results/`):

```powershell
python evaluation/run_baseline.py --output-json evaluation/artifacts/EXP-006-missing-policy/baseline.json --output-md evaluation/artifacts/EXP-006-missing-policy/baseline.md
python evaluation/run_agent.py --output-json evaluation/artifacts/EXP-006-missing-policy/agent.json --output-md evaluation/artifacts/EXP-006-missing-policy/agent.md
python evaluation/compare.py --baseline evaluation/artifacts/EXP-006-missing-policy/baseline.json --agent evaluation/artifacts/EXP-006-missing-policy/agent.json --output-json evaluation/artifacts/EXP-006-missing-policy/comparison.json
```

## Compare

| Field | Control (EXP-INITIAL-COMPARISON) | EXP-006 |
|---|---|---|
| Artifacts | `evaluation/artifacts/exp-initial-comparison/` | `evaluation/artifacts/EXP-006-missing-policy/` |
| `comparison_id` | `comparison-20260829T123158Z` | `comparison-20260829T124600Z` |
| Baseline / agent run ids | `baseline-20260829T123106Z` / `agent-20260829T123136Z` | `baseline-20260829T124522Z` / `agent-20260829T124543Z` |
| `case_lists_identical` | true (001–012) | true (001–012) |
| `n_cases_failed` | 1 (005 both sides) | **0** |
| Official aggregate WIS | **null** | baseline **0.9153**, agent **1.1343** |
| `wis.relative_improvement` | null | **−0.2392** (agent worse) |
| Human interventions | 11 | 12 (005 now also WARNs) |

Case **005** WIS: both sides **0.3789** (`relative_improvement` 0). Cases
**003 / 009 / 010** remain agent WIS losses vs baseline (same failure modes as
the control). Catalog CSVs were not edited.

## Keep / Remove

**Keep.** Official WIS is now defined over the full catalog. The agent is
still worse than baseline on that headline; this change does not claim a WIS
win. It is required infrastructure so later experiments can be scored.

## Document

This record. Changelog index. Methodology: named train-only fill in the
evaluation harness; source files under `data/evaluation/` are not overwritten.

## Problem observed

Official aggregate WIS was null while 005 failed on both harnesses.

## Change made

Named `linear_interpolate_train` on the training copy after split, both
harnesses.

## Evaluation command

Same three commands as **Run same benchmark**.

## Baseline result

`evaluation/artifacts/EXP-006-missing-policy/baseline.json`
`evaluation_run_id`: `baseline-20260829T124522Z`
Official aggregate WIS **0.9153325914744158**; `n_cases_failed` 0.

## New result

`evaluation/artifacts/EXP-006-missing-policy/agent.json`
`evaluation_run_id`: `agent-20260829T124543Z`
Official aggregate WIS **1.1343029712510242**; `n_cases_failed` 0;
`human_intervention_count` 12.

## Improvement

Official WIS became non-null. Agent vs baseline
`wis.relative_improvement` **−0.2392** (agent worse). Not a product win.

## Failure cases

None (`errors` empty). 003/009/010 still lost on WIS vs baseline.

## Decision

**Keep.**

## Lesson learned

A missing-value catalog case nulls official WIS until a named, train-only
policy exists. Silent fill in fitters would hide the failure.
