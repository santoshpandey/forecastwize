# Evaluation series (generated)

These CSVs are the **shared** ForecastWize evaluation cases. Baseline and any
advanced/agent path must use the same files, splits, and seeds.

Do **not** hand-edit these files. They are produced by:

```text
python -m evaluation.cases.generators
```

from the repository root (see `evaluation/cases/case_registry.yaml` and
`evaluation/cases/generators/`).

## Layout

Each file is `history_length` training rows followed by `forecast_horizon`
holdout rows on a regular timestamp grid. The origin is the last training
timestamp. There is no random row shuffle.

Columns: `timestamp`, `value`, `series_id`. Cases 008 and 012 also include
`context` and `event`. Missing values (case 005) are empty `value` cells.

## Scores

This directory is **data**, not results. There is no WIS table here. Official
scores come only from a future evaluation harness writing
`evaluation/artifacts/<evaluation_run_id>/`.
