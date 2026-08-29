# EXP-001 Conventional baseline harness

- **Kind:** baseline
- **Status:** executed
- **Date:** 2026-08-29

## Hypothesis

A conventional, non-agent path — rolling-origin backtest on **training rows
only**, then fit the selected named baseline and score the holdout — can be run
on the shared 12-case catalog with WIS as the official metric, without an LLM
and without dropping failed cases from the aggregate.

## Problem observed

Before this experiment there was no executable baseline on the catalog: no
`evaluation_run_id`, and no honest official WIS (including failures).

## Change made

Implemented `python evaluation/run_baseline.py`: load `case_registry.yaml` and
`data/evaluation/*.csv`, expanding-window backtest on train, select by official
backtest WIS (with a documented fallback fit order), score holdout with
`evaluation/metrics.py` (which calls `app.forecasting.metrics`).

## Evaluation command

```powershell
python evaluation/run_baseline.py
```

## Baseline result

This run **is** the baseline. There is no prior scored system to compare.

Record: `evaluation/results/baseline.json`  
`evaluation_run_id`: `baseline-20260829T071344Z`  
`git_commit` in that file: `54c0a145b55808e8f68474f0485c80cb430dbcd3`  
`case_list`: 001–012 (identical to the registry)

Official aggregate fields `wis`, `smape`, `wmape`, `mase`, `interval_coverage`,
and `interval_width` are **null** in that JSON because one case failed. That is
the headline, not a completed-only mean.

## New result

Same as baseline result (establishing run). Human-readable companion:
`evaluation/results/baseline.md`.

## Improvement

Not applicable. This experiment defines the reference, it does not claim a
delta vs another system.

## Failure cases

From `evaluation/results/baseline.json` `errors`:

- **005** (`ForecastInterfaceError`): non-finite training values; models do not
  impute or drop them.

`aggregate.n_cases_failed` is 1; `n_cases_completed` is 11.

## Decision

**Keep** this harness as the conventional baseline. Failed cases remain in the
official aggregate. Do not treat `wis_completed_only` in the JSON as the
headline.

## Lesson learned

A catalog with a missing-value case will null official WIS unless imputation is
an **explicit**, logged policy. Silent fill would hide the failure and break
the evaluation rules.
