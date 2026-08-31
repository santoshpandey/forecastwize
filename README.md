# ForecastWize

Agentic forecasting and decision support for business and operations analysts.
Agents reason over diagnostics and evidence. **Deterministic Python** owns every
yhat, interval, and metric. An LLM must never invent a forecast number.

**Official result (do not remember a percentage):**
`evaluation/results/comparison.json`, `comparison_id`
`comparison-20260830T030644Z`. Official advanced path is **EXP-010**
(`selection_policy=exp010`, `origin_planning=model_specific`,
`EXP010_LAST_TO_EARLIER_VETO=5.0`).

| Official WIS | Value |
|---|---|
| Baseline | **0.9153325914744158** (~0.91533) |
| Advanced | **0.7939144093884205** (~0.79391) |
| Relative improvement | **0.13264925035654543** (~**13.26%**) |

12 / 12 cases completed, 0 failed. Holdout: **8** advanced wins, **2**
baseline wins, **2** ties. Case **012** remains a baseline win. Do not
claim every case or every metric improved.

**Reproduction (pins, seeds, commands):** [docs/reproduction.md](docs/reproduction.md).

---

## Problem

Analysts must produce a point forecast and intervals that others will use to
staff, buy, or commit budget. A single default model, spreadsheet gut feel, or
an LLM that emits MAPE all fail the same way: the number is hard to audit,
easy to leak future data into, and easy to overtrust.

The product problem is **defensible procedure under uncertainty**, not chat.

## Target user

**Primary:** business and operations analysts (demand, inventory, staffing,
capacity) who can read a series and a metric table, but are not full-time
forecasting researchers.

**Secondary:** a reviewer who did not write the code must rerun the shared
catalog and see the same `case_list` and scores from artifacts.

## Bottleneck

The scarce resource is **trustworthy procedure**:

1. Pick a method that fits the series (trend, seasonality, intermittency, breaks).
2. Avoid leakage and silent preprocessing.
3. Score intervals (WIS), not only a point error.
4. Explain the choice with backtest evidence, not authority.
5. Stop and ask a human when evidence is weak.

An agent is useful only if it **orchestrates tools and checks**. It must not
replace the statistician with a paragraph of invented numbers.

## Solution

ForecastWize splits the work:

| Layer | Owns |
|---|---|
| Agents / orchestrator | Strategy hypotheses, tool requests, verification challenge, bounded retry, evidence-cited narrative, human checkpoint |
| Deterministic Python | Fit, yhat, intervals, backtests, WIS and secondaries, named train-only missing-value fill |
| API / UI | Transport and display of backend values; labeled Accept / Reject / Review |

The graph is an explicit typed state machine (`run_orchestrator`). Official
advanced selection is **EXP-010**: model-specific valid backtest origins plus
a deterministic last/earlier fold-WIS veto (`R=5`), then official backtest
WIS among models that pass. The LLM/agent does **not** generate yhat, WIS, or
the veto. Generation is a separate `run_baseline_forecast` call. The verifier
**challenges** the forecast (PASS / WARN / FAIL). FAIL retries only if an
untried **selectable** model has strictly better official backtest WIS.

## Baseline

Non-agent path: `python evaluation/run_baseline.py`.

- Same 12-case catalog, CSVs, splits, seeds, and metric functions as the agent.
- Expanding-window backtest on **training rows only**.
- Select by official backtest WIS among `naive`, `seasonal_naive`, `ets`,
  `arima` (documented fallback order if needed).
- Named policy `linear_interpolate_train` on the training copy after split
  (holdout and source CSVs are not filled).
- No LLM. No graph.

Cited run: `evaluation/results/baseline.json`,
`evaluation_run_id` `baseline-20260830T020244Z`.

## Advanced architecture

Agent path: `python evaluation/run_agent.py` → `run_orchestrator` on the same
train split (holdout is **not** passed into the graph).

Nodes: START → PROFILE → DIAGNOSE → CONTEXT → STRATEGY → BACKTEST → FORECAST
→ VERIFY → RETRY_OR_ACCEPT → ANALYZE → FINALIZE.

- STRATEGY shortlist is a **hypothesis**.
- BACKTEST executes the full allow-list (`BASELINE_MODEL_IDS`).
- FORECAST calls `run_baseline_forecast` with the selected `strategy_id`.
- VERIFY must run before accept. WARN waits for a human checkpoint.
- Trajectory is append-only JSONL (`app/evidence`).

Cited run: `evaluation/results/agent.json`,
`evaluation_run_id` `agent-20260830T030413Z`
(`selection_policy=exp010`).

Details: [docs/architecture.md](docs/architecture.md),
[docs/agent-design.md](docs/agent-design.md).

## Setup

Requirements: Python **3.12+**, Node.js **22+**, npm **10+**. Optional: GNU
Make, Docker Compose. Windows without Make: `.\make.cmd` or the PowerShell
commands below.

```bash
cp .env.example .env
make setup
```

Windows PowerShell:

```powershell
copy .env.example .env
python -m pip install -r backend/requirements.txt
Set-Location frontend; npm ci; Set-Location ..
```

`.env` is gitignored. Leave `OPENAI_API_KEY` empty. The orchestrator does not
call an LLM. Never put real keys in `.env.example` or in git.

## Run commands

```bash
make dev
```

- API: http://127.0.0.1:8000/health
- UI: http://localhost:3000

Separate processes: `make run-backend` and `make run-frontend`.

Docker (host binds **127.0.0.1** only; see [docs/security.md](docs/security.md)):

```bash
docker compose up --build
```

Tests: `make test`. Full lint + pytest + frontend build: `make check`.
Windows: `.\scripts\check.ps1`.

## Evaluation

Identical cases for both systems. Catalog 001–012 (includes adversarial 012).
Primary metric: official **WIS** over the **full** case list (failures are not
dropped). Secondaries: sMAPE, WMAPE, MASE, interval coverage, interval width,
runtime, human-intervention count.

From the repository root:

```bash
make evaluate-baseline
make evaluate-agent
make compare
```

Equivalent:

```bash
python evaluation/run_baseline.py
python evaluation/run_agent.py
python evaluation/compare.py
```

Re-running **overwrites** `evaluation/results/*.json` and mints a new
`evaluation_run_id`. Cited IDs: [docs/reproduction.md](docs/reproduction.md).
Catalog, splits, and metric rules: [docs/evaluation.md](docs/evaluation.md).

GitHub Actions **Evaluation** is the same harnesses on demand
(`.github/workflows/evaluation.yml`). It is not commit CI and does not use
API keys.

## Results

Source of truth: `evaluation/results/comparison.json`
(`comparison_id` `comparison-20260830T030644Z`;
`case_lists_identical` true; `git_commit`
`524837b0ea8a9378f7d9d6601d080eceff602431`).

| Field in that JSON | Value |
|---|---|
| `aggregate.metrics.wis.relative_improvement` | **0.13264925035654543** (~13.26%) |
| `aggregate.metrics.wis.baseline` | `0.9153325914744158` |
| `aggregate.metrics.wis.agent` | `0.7939144093884205` |
| `aggregate.n_cases_failed` | 0 / 0 (all 12 cases) |
| Holdout case outcomes | advanced **8**, baseline **2**, ties **2** |
| `aggregate.human_intervention_count` | baseline 0, agent **12** (checkpoints opened, not human decisions) |

Do not claim the advanced system wins every case. Case **012** still loses
holdout WIS to baseline (naive 3.114 vs seasonal_naive 1.378). Do not cite
`wis_completed_only` as the headline. Isolated experiment pairs and the
pre-promotion official archive live under `evaluation/artifacts/` and are
summarized in [docs/changelog.md](docs/changelog.md).

### Biggest improvement

Official catalog WIS improved **13.26%** vs the conventional baseline
(`relative_improvement` **0.13264925035654543**). The largest per-case
holdout WIS gain on the official pair is case **001** (ARIMA vs naive,
`relative_improvement` **0.894**).

Earlier experiment recovery (not the current headline): case **003** WIS
`relative_improvement` was **-5.145…** in EXP-006 and **0.0** in EXP-007
after retry-only-if-better-WIS.

### Biggest failure

Case **012** (adversarial regime change) still loses holdout WIS: advanced
naive **3.114** vs baseline seasonal_naive **1.378**. EXP-009 had selected
ETS at **22.83**; the EXP-010 veto cut that catastrophe but did not make
the advanced path better than baseline on this case. Case **007** also
loses. Human interventions remain **12** vs **0**.

### Removed experiment

**EXP-009** model-specific origins without the instability veto. Isolated
WIS `relative_improvement` **−1.662**. Default was restored, then EXP-010
was promoted. Artifacts:
`evaluation/artifacts/EXP-009-ets-arima-min-train/`.

### Main engineering lesson

A hypothesis (strategy shortlist, verifier FAIL) is not a license to change
the numbers. Execute the same candidate set and metric code as the baseline;
retry only when official backtest WIS is strictly better; use a **named**
train-only missing policy instead of silent fill. Agents still do not emit
yhat.

## Limitations

- Official catalog WIS improved **13.26%**, but the advanced path does
  **not** win every holdout case (8 / 2 / 2). Case **012** still loses
  to baseline. sMAPE / WMAPE are not the headline; do not claim all
  metrics improved.
- Automated evaluation opens a human checkpoint on every case (WARN).
  `human_intervention_count` **12** means **checkpoints opened**, not
  12 human decisions. Official catalog records **0** human decisions.
  One real Accept is in the interactive demo
  ([docs/human-in-the-loop-demo.md](docs/human-in-the-loop-demo.md)).
- Authentication is **not started**. Do not publish the API on a shared
  network ([docs/security.md](docs/security.md)).
- No vendor LLM is wired. `OPENAI_API_KEY` may be empty. Deterministic
  Python selects the model from backtest / robustness evidence; an LLM
  does not pick the winner.
- Catalog is synthetic (12 fixed cases). Optional ML was not added (no
  evaluation evidence that it would improve WIS).
- Official catalog evaluation persists one JSONL per case under
  `evaluation/results/trajectories/` (`holdout_passed_to_graph` remains
  false). See [docs/trajectory-evidence.md](docs/trajectory-evidence.md).

## Reproducibility

Pins, case seeds, and the cited `evaluation_run_id`s are in
[docs/reproduction.md](docs/reproduction.md). Same catalog, same metric
module (`evaluation/metrics.py` calls `app.forecasting.metrics`), same
split rule. Failed cases stay in the official mean. Commands in this README
match the Makefile / `python evaluation/*.py` entry points.

## Agent trajectories

Append-only JSONL via `backend/app/evidence/`. Schema and reviewer sequence:
[trajectories/README.md](trajectories/README.md).

- **Checked-in examples:** `backend/tests/fixtures/trajectories/*.jsonl`
  (success, verification retry, tool failure).
- **UI / API runs:** `{run_id}.jsonl` under the API store (`data/api/`,
  gitignored) plus `GET /runs/{id}/trajectory`.
- **Catalog harness:** `evaluation/run_agent.py` defaults
  `persist_trajectory=True` and writes
  `evaluation/results/trajectories/<evaluation_run_id>/case_*.jsonl`.
  Fixture JSONL under `backend/tests/fixtures/trajectories/` is not a
  catalog run.
- **Interactive human demo:** one real Accept / Reject / Review under
  `evaluation/artifacts/human-demo/`. See
  [docs/human-in-the-loop-demo.md](docs/human-in-the-loop-demo.md).
  Official catalog still has 12 opened checkpoints and 0 human decisions.

Each line includes `run_id`, `agent_id`, `timestamp`, hashed input summary,
`tool_invocation` / `tool_output_ref`, `decision`, `evidence_ids`,
`retry_number`, and `final_status`. Raw series and secrets are omitted /
redacted. Failures are kept.

## Status

| Area | State |
|---|---|
| FastAPI + Next.js analyst UI | **Implemented** |
| Deterministic models | **Implemented** (naive, seasonal naive, ETS, ARIMA) |
| Agent graph / verifier / checkpoints | **Implemented** |
| Evaluation catalog + baseline + agent + compare | **Implemented** |
| Authentication | **Not started** |
| Production database | **Not used** (files only) |
| Vendor LLM | **Not integrated** |

## Documentation

- [Product requirements](docs/product-requirements.md)
- [Architecture](docs/architecture.md)
- [Agent design](docs/agent-design.md)
- [Forecasting methodology](docs/forecasting-methodology.md)
- [Evaluation](docs/evaluation.md)
- [Experiments](experiments/README.md)
- [Reproduction](docs/reproduction.md)
- [Security](docs/security.md)
- [Demo notes (judges)](demo-notes.md)
- [Demo script](docs/demo-script.md)
- [Human-in-the-loop demo](docs/human-in-the-loop-demo.md)
- [Changelog](docs/changelog.md)

## Layout

```
backend/       FastAPI adapter (no forecast math in handlers)
frontend/      Next.js UI
data/          Originals; generated eval CSVs in data/evaluation/; API store in data/api/
evaluation/    Shared catalog + harnesses + results/ + artifacts/
experiments/   Named EXP-*.md records
trajectories/  Runtime traces (gitignored except README); fixtures under backend/tests/
docs/          Product documentation
scripts/       setup, test, dev, check
```
