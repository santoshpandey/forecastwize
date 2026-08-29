# EXP-003 Anomaly and data diagnostics

- **Kind:** iteration
- **Status:** implemented; **not** measured as an isolated A/B
- **Date:** 2026-08-29

## Hypothesis

Explicit, non-mutating diagnostics (quality, outliers, rolling anomalies,
trend, seasonality, structural breaks) give the graph structured evidence for
risks and candidate shortlists **without** silently editing the series or
emitting yhat.

## Problem observed

Forecasting on dirty series without a recorded diagnostic would hide missingness
and outliers. Silent clip/fill would violate the constitution. Agents must not
invent column or event facts.

## Change made

- Deterministic tools in `backend/app/tools/data_tools.py` wrapping `app.data`
- Data Detective (`run_data_detective`) cites evidence IDs, labels hypotheses,
  does not modify data or forecast
- Orchestrator PROFILE/DIAGNOSE nodes call those paths before strategy

## Evaluation command

Same shared harness. No “diagnostics on vs off” evaluation run was recorded.

```powershell
python evaluation/run_agent.py
```

Catalog cases that **exercise** related challenges (not a measured ablation):
006 outliers, 007 structural break, 005 missing values (see
`evaluation/cases/case_registry.yaml`).

## Baseline result

Not measured in isolation. EXP-001 does not run the detective; it still fails
**005** on non-finite train values.

## New result

Not measured in isolation. Detective unit tests exist; they are not official
WIS. The full agent run (`agent-20260829T090636Z`) still fails **005** with a
non-finite training-value error (see `evaluation/results/agent.json` `errors`).

## Improvement

**Not computed.** Diagnostics are not allowed to invent a better yhat. Any
holdout change from this slice would need a dedicated pair of runs.

## Failure cases

- **005** remains failed on the agent harness (non-finite train values; no
  silent imputation).
- Isolated diagnostic false-positive/false-negative rates were not scored on
  the catalog.

## Decision

**Keep** explicit detect-and-record diagnostics. **Do not** add silent
imputation to chase official WIS. If a missing-value **policy** is added later,
it must be named, logged, and re-evaluated as a new experiment.

## Lesson learned

Detecting anomalies is not the same as repairing them. Case 005 shows the
catalog will keep official WIS at null until missingness is handled as an
explicit, evaluated policy — or the case is accepted as a standing failure.
