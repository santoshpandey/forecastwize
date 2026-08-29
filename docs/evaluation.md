# Evaluation

## Implemented

- Shared catalog: `evaluation/cases/case_registry.yaml` (12 synthetic cases)
- Deterministic generators under `evaluation/cases/generators/`
- Generated CSVs under `data/evaluation/` (regenerate; do not hand-edit)
- Split rule: first `history_length` rows are train; the next `forecast_horizon`
  rows are holdout. Timestamps are strictly increasing.
- Evaluation dashboard: `GET /evaluations/dashboard` serves
  `evaluation/results/comparison.json`; UI at `/evaluation`. Losses, zeros, and
  null official WIS are shown. Improvement percentages are the artifact's
  `relative_improvement`, not browser math.

| ID | Challenge |
|---|---|
| 001 | trend |
| 002 | stable seasonality |
| 003 | trend + seasonality |
| 004 | noisy trend |
| 005 | missing values |
| 006 | outliers |
| 007 | structural break |
| 008 | event/context change |
| 009 | intermittent demand |
| 010 | short history |
| 011 | long horizon |
| 012 | adversarial regime change |

There is **no** hard-coded improvement figure used as source of truth. Run the
harnesses and read `evaluation/results/comparison.json`. Named experiments
(hypothesis, commands, decisions) are in [experiments/README.md](../experiments/README.md);
the summary is [changelog.md](changelog.md). Exact pins, seeds, and
`evaluation_run_id`s: [reproduction.md](reproduction.md).

From the repository root:

```bash
make evaluate-baseline
make evaluate-agent
make compare
```

Equivalent: `python evaluation/run_baseline.py`, `python evaluation/run_agent.py`,
`python evaluation/compare.py`. GitHub Actions **Evaluation** is the same
harnesses on demand (`.github/workflows/evaluation.yml`); it is not part of
commit CI and does not use API keys.

The harness loads **exactly** the registered cases, backtests on training rows
only, scores holdout **WIS** (primary) plus sMAPE, WMAPE, MASE, coverage, and
interval width, and records failures, runtime, configuration, and git commit.
After the train/holdout split, both harnesses apply named policy
`linear_interpolate_train` to the **training** copy only (EXP-006). Isolated
comparison copies live under `evaluation/artifacts/EXP-*/` and
`evaluation/artifacts/exp-initial-comparison/`.

The agent harness (`python evaluation/run_agent.py`) uses the **same** case
list, CSVs, splits, seeds, and metric functions. Comparison
(`python evaluation/compare.py`) writes `evaluation/results/comparison.json`
with per-case and aggregate deltas computed from those files. Failed cases stay
in the record. Improvement percentages are not hard-coded.

## Cited official pair

Read `evaluation/results/comparison.json` (`comparison_id`
`comparison-20260829T125254Z`; baseline `baseline-20260829T125209Z`; agent
`agent-20260829T125231Z`; `case_lists_identical` true).

| JSON field | Recorded value |
|---|---|
| `aggregate.metrics.wis.relative_improvement` | 0.0 |
| `aggregate.n_cases_failed` (baseline / agent) | 0 / 0 |
| `aggregate.human_intervention_count` | 0 / 12 |
| `errors` | both empty |

Do not paste a different improvement percentage. Isolated experiment copies:
`evaluation/artifacts/EXP-006-missing-policy/`,
`EXP-007-retry-backtest-wis/`, `EXP-008-full-candidates/`, and the first
catalog control `evaluation/artifacts/exp-initial-comparison/`.

**Biggest improvement (experiments):** case 003 WIS `relative_improvement`
from **-5.145124275946384** in EXP-006 comparison to **0.0** in EXP-007 (and
the official pair). EXP-006 made official WIS non-null.

**Biggest failure (official pair):** no WIS win vs baseline; 12 human
interventions.

**Removed experiment:** none.

No further catalog layout work is **Planned**. Optional ML remains out of
scope until a catalog pair shows WIS improvement.
