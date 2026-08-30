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
`python evaluation/compare.py`. `run_agent.py` also writes real per-case
trajectories under `evaluation/results/trajectories/<evaluation_run_id>/`
([trajectory-evidence.md](trajectory-evidence.md)). GitHub Actions **Evaluation**
is the same harnesses on demand (`.github/workflows/evaluation.yml`); it is not
part of commit CI and does not use API keys.

Evaluation `human_intervention_count` is checkpoints opened, not human
decisions.

The harness loads **exactly** the registered cases, backtests on training rows
only, scores holdout **WIS** (primary) plus sMAPE, WMAPE, MASE, coverage, and
interval width, and records failures, runtime, configuration, and git commit.
After the train/holdout split, both harnesses apply named policy
`linear_interpolate_train` to the **training** copy only (EXP-006). Isolated
comparison copies live under `evaluation/artifacts/EXP-*/` and
`evaluation/artifacts/exp-initial-comparison/`.

The agent harness (`python evaluation/run_agent.py`) uses the **same** case
list, CSVs, splits, seeds, and metric functions. The official advanced
configuration is promoted EXP-010 (`selection_policy=exp010`): model-specific
valid origins plus the frozen last/earlier fold-WIS veto. Comparison
(`python evaluation/compare.py`) writes `evaluation/results/comparison.json`
with per-case and aggregate deltas computed from those files. Failed cases stay
in the record. Improvement percentages are not hard-coded.

## Cited official pair

Read `evaluation/results/comparison.json` (`comparison_id`
`comparison-20260830T030644Z`; baseline `baseline-20260830T020244Z`; agent
`agent-20260830T030413Z`; `case_lists_identical` true).

| JSON field | Recorded value |
|---|---|
| `aggregate.metrics.wis.baseline` | 0.9153325914744158 |
| `aggregate.metrics.wis.agent` | 0.7939144093884205 |
| `aggregate.metrics.wis.relative_improvement` | 0.13264925035654543 (~13.26%) |
| Holdout wins / losses / ties | 8 / 2 / 2 |
| `aggregate.n_cases_failed` (baseline / agent) | 0 / 0 (all 12 cases) |
| `aggregate.human_intervention_count` | 0 / 12 (checkpoints opened, not human decisions) |
| `errors` | both empty |

Do not paste a different improvement percentage. Do not claim a win on every
case. Isolated experiment copies:
`evaluation/artifacts/EXP-006-missing-policy/`,
`EXP-007-retry-backtest-wis/`, `EXP-008-full-candidates/`,
`EXP-009-ets-arima-min-train/` (WIS failed),
`EXP-010-robust-model-selection/` (frozen isolate of this official path),
`pre-exp010-promotion/` (previous official EXP-008 pair), and the first
catalog control `evaluation/artifacts/exp-initial-comparison/`.

**Biggest improvement (official pair):** catalog WIS **13.26%**; largest
per-case holdout gain is **001**.

**Biggest failure (official pair):** case **012** still loses holdout WIS
(naive 3.114 vs baseline seasonal_naive 1.378). EXP-009 ETS was 22.83.
Automated evaluation opened 12 checkpoints and recorded 0 human decisions.

**Removed experiment:** EXP-009 as the default (planner without veto).

No further catalog layout work is **Planned**. Do not start EXP-011 in this
promotion.
