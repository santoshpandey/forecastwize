# Evaluation

Shared case catalog, baseline harness, agent harness, and comparison. This
package must not import FastAPI or Next.js. Metric formulas live in
`backend/app/forecasting/metrics.py` and are invoked from `evaluation/metrics.py`,
not copied.

## Implemented

- `evaluation/cases/case_registry.yaml` — 12 fixed synthetic cases (001–012)
- `evaluation/cases/generators/` — deterministic generators
- Generated CSVs at `data/evaluation/`
- Baseline harness: `python evaluation/run_baseline.py`
  - loads the registry and each CSV
  - expanding-window backtest on **training rows only**
  - holdout WIS (primary) plus secondaries
  - failed cases kept in the official aggregate
  - writes `evaluation/results/baseline.json` and `evaluation/results/baseline.md`
- Agent harness: `python evaluation/run_agent.py`
  - **the same** registered `case_list`, CSVs, splits, seeds, and metric functions
  - `run_orchestrator` on training rows only (holdout is not passed into the graph)
  - writes `evaluation/results/agent.json` and `evaluation/results/agent.md`
- Comparison: `python evaluation/compare.py`
  - requires identical case lists
  - computes WIS, sMAPE, WMAPE, MASE, coverage, width, runtime, failures, and
    human-intervention counts from the two JSON files
  - never hard-codes improvement percentages
  - writes `evaluation/results/comparison.json`

Regenerate CSVs:

```powershell
python -m evaluation.cases.generators
```

Run baseline, agent, and comparison (from the repository root):

```bash
make evaluate-baseline
make evaluate-agent
make compare
```

```powershell
python evaluation/run_baseline.py
python evaluation/run_agent.py
python evaluation/compare.py
```

Official improvement vs the agent is the `relative_improvement` field for WIS in
`evaluation/results/comparison.json` for that pair of run ids. Do not paste
remembered percentages as the source of truth. Named experiments:
[experiments/README.md](../experiments/README.md).
