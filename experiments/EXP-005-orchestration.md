# EXP-005 Agent orchestration vs baseline

- **Kind:** final
- **Status:** executed
- **Date:** 2026-08-29

## Hypothesis

Running the explicit graph (PROFILE → … → FINALIZE) on **exactly** the same
cases, splits, seeds, and metric functions as EXP-001 yields a comparable
advanced system whose official WIS can be compared without leaking holdout into
the graph.

## Problem observed

Child agents existed as separate pipelines. Without a single orchestrated run
on the catalog, there was no paired `evaluation_run_id` for baseline vs
advanced.

## Change made

- `run_orchestrator` state machine, bounded retries, verification required
  before accept
- `python evaluation/run_agent.py` calls that graph on **train** only, then
  scores holdout with the same `score_holdout` as the baseline
- `python evaluation/compare.py` refuses mismatched `case_list` and writes
  computed deltas (never hard-coded)

## Evaluation command

```powershell
python evaluation/run_baseline.py
python evaluation/run_agent.py
python evaluation/compare.py
```

Paired artifacts for this experiment **at the time it was written**:

- Baseline: `evaluation/results/baseline.json` (`baseline-20260829T071344Z`)
- Agent: `evaluation/results/agent.json` (`agent-20260829T090636Z`)
- Comparison: `evaluation/results/comparison.json` (`comparison-20260829T090720Z`)

Those files were later overwritten by
[EXP-INITIAL-COMPARISON](EXP-INITIAL-COMPARISON.md). Do not treat the current
JSON on disk as this pair.
- `case_lists_identical`: true (001–012)
- `git_commit` recorded in the comparison file:
  `54c0a145b55808e8f68474f0485c80cb430dbcd3`

## Baseline result

See EXP-001 and `evaluation/results/baseline.json`. Official aggregate WIS is
**null** (`n_cases_failed` = 1).

## New result

See `evaluation/results/agent.json`. Official aggregate WIS is **null**
(`n_cases_failed` = 1). `human_intervention_count` is 0.

## Improvement

**Official (headline) WIS relative_improvement is null** in
`evaluation/results/comparison.json` `aggregate.metrics.wis`, because official
means include the failed case on both sides.

Do not substitute `wis_completed_only` as the product claim. Per-case WIS
deltas (some zero, some not) are in `comparison.json` `per_case`; they are not
copied here.

Other aggregate fields in that comparison file (failures, human interventions)
are computed from the two JSONs. Failures: 1 vs 1.

## Failure cases

Both systems, case **005**, `ForecastInterfaceError`, non-finite training
values (messages in `comparison.json` `errors`). No case was dropped from
`case_list`.

## Decision

**Keep** the orchestrator as the advanced evaluation path. **Do not** claim an
official WIS win while headline WIS is null. A future experiment must either
add an explicit missing-value policy (new EXP) or accept 005 as a standing
failure and still refuse to headline completed-only WIS.

## Lesson learned

Identical case lists and shared metrics make comparison valid even when the
headline is null. The graph did not fix missingness. Runtime and per-case
movements in `comparison.json` are not a substitute for official WIS.
