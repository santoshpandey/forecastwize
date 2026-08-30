# Product requirements

ForecastWize is an **agentic forecasting decision-support** application for business
and operations analysts. It helps an analyst produce a forecast they can defend:
a numerical prediction from deterministic models, plus an explanation of why a
strategy was chosen, what could go wrong, and whether a human should intervene.

**Hackathon questions this document must keep answering**

| Question | This product’s answer |
|---|---|
| Who has the problem? | Analysts who must forecast operations or demand and justify the number. |
| What bottleneck makes it worth solving? | Choosing a method, checking leakage/intervals, and writing a defensible rationale under time pressure — not “an LLM that emits a number.” |
| Does the agent solve it well? | **Measured, not assumed.** Official proof is WIS on the shared 12-case list vs the defined baseline. Current pair: `evaluation/results/comparison.json` (`comparison-20260830T030644Z`). `aggregate.metrics.wis.relative_improvement` is **0.13264925035654543** (~13.26%). The advanced path does not win every case (8 / 2 / 2). |
| Can another person reproduce the result? | **Yes, from artifacts.** Same cases, seeds, pins, and scripts: [reproduction.md](reproduction.md). Re-running mints a new `evaluation_run_id` and overwrites `evaluation/results/` unless you copy the cited files aside. |

**Status of this document vs the repo**

- Requirements below are the product contract.
- Anything not built yet is labeled **Planned**.
- **Implemented:** FastAPI REST adapters, Next.js analyst UI, four named
  baselines, orchestrator graph, verifier, human checkpoints, shared catalog,
  baseline + agent + compare harnesses, trajectory JSONL.
- Scores live in evaluation JSON. This file is not the score table.

---

## 1. Problem statement

Analysts are asked for a forecast (and often an interval) that others will use to
staff, buy, or commit budget. Spreadsheet “gut feel,” a single default model, or
an LLM that invents MAPE all fail the same way: the number is hard to audit, easy
to leak future data into, and easy to overtrust.

The problem is **decision support under uncertainty**, not chat. ForecastWize must
separate:

- **Reasoning** (what strategy to try, what risks remain) — agents, **Implemented**
  (`run_orchestrator`, `POST /runs`)
- **Numbers** (yhat, intervals, WIS, coverage, backtests) — deterministic Python
  (**Implemented**)

An LLM must never be the source of numerical truth. No vendor LLM is wired today.

---

## 2. Target user

**Primary:** business and operations analysts (demand, inventory, staffing,
capacity) who can read a series and a metric table, but are not full-time
forecasting researchers.

**Secondary (hackathon judges / reviewers):** someone who did not write the code
must rerun evaluation and see the same case list and scores from artifacts.

**Not the primary user:** end customers of a consumer app; unattended autonomous
trading or pricing bots.

---

## 3. User bottleneck

The scarce resource is **trustworthy procedure**, not tokens:

1. Pick a method that fits the series (trend, seasonality, intermittency, breaks).
2. Avoid leakage and silent preprocessing.
3. Produce intervals and know if they are calibrated — not only a point MAPE.
4. Explain the choice with evidence (backtest), not authority.
5. Know when to stop and ask a human.

That bottleneck is worth an agent only if the agent **orchestrates tools and
checks**, rather than replacing the statistician with a paragraph.

Whether ForecastWize relieves the bottleneck is an **evaluation question**.
On the cited official pair (`comparison-20260830T030644Z`, EXP-010),
official WIS improved **~13.26%** (baseline `0.9153325914744158`,
advanced `0.7939144093884205`). The advanced path does not win every
holdout case (8 / 2 / 2); case **012** still loses. Automated evaluation
opens a checkpoint on every case (`human_intervention_count` 12 =
**checkpoints opened**, not human decisions; **0** human decisions on
the catalog run). See [changelog.md](changelog.md).

---

## 4. User goals

1. Obtain a point forecast and prediction intervals for an explicit horizon and frequency.
2. See **why** a strategy was selected (backtest evidence IDs), not only which name won.
3. See risks, uncertainty, and failed checks instead of a greenwashed summary.
4. Compare the advanced path to a **fixed baseline** on the **same** cases.
5. Reproduce a run (commit, config, seeds, artifacts) or hand the folder to a colleague.
6. Approve or reject high-impact steps explicitly (**Implemented** UI/API).

---

## 5. Non-goals

- LLM-generated yhat, intervals, or metrics.
- Hard-coded leaderboard percentages or notebook-pasted “wins.”
- Authentication, multi-tenant SaaS, or a production database in the current scope.
- Autonomous execution of business actions (orders, pricing, hiring) without a human.
- Optional heavy ML as a default; add it only if evaluation evidence justifies it.
- Claiming a WIS win when `relative_improvement` is 0.0 or null.

---

## 6. Core user journey

**Implemented** in the UI (numbers still come only from the API):

1. Analyst uploads a validated CSV. Original data is not overwritten.
2. Diagnostics screen shows row count, date range, frequency, missing periods, anomalies, seasonality, and structural break from Python tools.
3. Analyst sets horizon, frequency, coverage, and seed; `POST /runs` starts the graph.
4. Agent execution shows Data Detective → Forecast Strategist → Context Analyst → Backtesting → Forecast → Verification → Final Analysis.
5. Forecast, verification, and model-comparison screens display backend yhat, intervals, checks, and official backtest WIS. The browser does not compute WIS.
6. Evaluation comparison displays `evaluation/results/comparison.json` via `GET /evaluations/dashboard`. Optional live catalog run: `POST /evaluations/compare`.
7. When a checkpoint is required, Accept / Reject / Review are explicit labeled controls. Navigation does not auto-approve. Rejected recommendations stay on the run trajectory. Source data is not modified.

---

## 7. Baseline experience

**Implemented and scored.** Non-agentic procedure:
`python evaluation/run_baseline.py`. Expanding-window backtest on training
rows, select by official backtest WIS among four named models, fit the winner,
score holdout with the shared metric module. Named
`linear_interpolate_train` on the train copy after split. No LLM.

Cited artifact: `evaluation/results/baseline.json`
(`baseline-20260830T020244Z`). Official scores are in that file, not here.
The superseded EXP-008 baseline (`baseline-20260829T125209Z`) is archived
at `evaluation/artifacts/pre-exp010-promotion/`.

HTTP `POST /forecasts` is the same named-model path (`run_baseline_forecast`)
for an uploaded series, not the catalog harness.

---

## 8. Advanced experience

**Implemented.** Data Detective, Forecast Strategist, Context Analyst, Verifier,
Forecast Analyst, and the orchestrator graph. They do not emit a new yhat.
BACKTEST executes the full allow-list; the strategy shortlist is a hypothesis.
FAIL retries only if official backtest WIS strictly improves.
`POST /runs` queues the graph. `POST /runs/{id}/checkpoint` records Accept,
Reject, or Review.

**Does the agent solve it well?** Official advanced is **EXP-010**
(`selection_policy=exp010`, `origin_planning=model_specific`, `R=5.0`).
Official WIS vs baseline improved **~13.26%**
(`relative_improvement` 0.13264925035654543 in
`comparison-20260830T030644Z`). Holdout outcomes: 8 / 2 / 2. Case 012 still
loses. Automated evaluation: 12 checkpoints opened, 0 human decisions.
See [evaluation.md](evaluation.md).

---

## 9. Functional requirements

| ID | Requirement | Status |
|---|---|---|
| F1 | Health API, REST adapters, typed health client | **Implemented** |
| F2 | Deterministic forecast, intervals, metrics, backtests | **Implemented** (library + `POST /forecasts`) |
| F3 | Common model interface; selection ≠ generation | **Implemented** (orchestrator selects from backtest then generates; `POST /runs`) |
| F4 | Time-aware splits; no ordinary-eval shuffle; no future leakage | Backtester + both eval harnesses **Implemented** |
| F5 | Explicit frequency, horizon, missing/anomaly policies; no overwrite of `data/` | Frequency/horizon **Implemented**; named train-only interpolate in eval harnesses **Implemented**; additional repair policies **Planned**; fitters still reject remaining NaN |
| F6 | Forecast metadata (model, train range, horizon, frequency, config, seed, `generated_at`) | **Implemented** on `ForecastResult` |
| F7 | Agent graph, approved tools, structured state/outputs, evidence IDs | **Implemented** (`orchestrator.py` + `POST /runs`) |
| F8 | Verifier that challenges, not summarizes | Deterministic checks + graph wiring **Implemented**; extra leakage probes **Planned** |
| F9 | Append-only trajectories under `trajectories/` / API store | JSONL + artifacts **Implemented** (`app/evidence`) |
| F10 | UI: loading/error/empty; warnings ≠ errors; visible agent state; backend as source of truth | Analyst journey **Implemented**; Accept/Reject/Review **Implemented** |
| F11 | Shared evaluation catalog (≥12 cases, including adversarial) | Catalog + baseline + agent + compare **Implemented** |
| F12 | Uploads validated (size, CSV, path safety) when uploads exist | **Implemented** (`POST /datasets`) |

---

## 10. Non-functional requirements

| ID | Requirement | Status |
|---|---|---|
| N1 | Python 3.12+, FastAPI, Pydantic, pytest, Ruff; Next.js + strict TypeScript | **Implemented** |
| N2 | No secrets in git; `.env.example` only; no keys in the client bundle | **Implemented** for current config |
| N3 | Structured logs; no secret logging; public vs internal errors | **Implemented** (adapter; `X-Request-ID`) |
| N4 | Pin dependencies for reproducible installs | **Implemented** (`backend/requirements.txt`, `frontend/package-lock.json`; [reproduction.md](reproduction.md)) |
| N5 | Forecasting/evaluation isolated from FastAPI and from agents | Forecasting + eval harnesses **Implemented** (no FastAPI import) |
| N6 | Tests at unit / API / agent / evaluation levels | Health + REST + config + baseline + backtest + catalog + harness + agent tests **Implemented**; frontend typecheck **Implemented**; GitHub Actions CI **Implemented** |
| N7 | File storage; no production DB unless later justified | **Implemented** (no DB) |

---

## 11. Human-in-the-loop requirements

**Implemented.** Explicit Accept / Reject / Review on `waiting_for_approval`
runs (`POST /runs/{id}/checkpoint`). The graph never auto-approves. Source
data is not modified.

- Required when data modification is proposed, forecast confidence is low,
  verification fails repeatedly, or material uncertainty remains.
- High-impact, irreversible, or poorly evidenced decisions wait for **explicit**
  approval (labeled control: what is pending and what happens next).
- No implicit auto-approve via navigation, default checkboxes, or silent timeouts.
- Rejected recommendations are appended to the run trajectory (`agent_id=human`).
- Human intervention **count** is recorded on the agent evaluation JSON and in
  `comparison.json`. On the cited official pair it is 12 **checkpoints
  opened**, not 12 human decisions (catalog records 0 `HUMAN_DECISION`).
- Agents may **recommend** review; they must not quietly accept a failed verifier.

---

## 12. Reproducibility requirements

A second person must be able to clone, install from documented commands, and:

1. Run checks, `/health`, and the three eval scripts as in
   [reproduction.md](reproduction.md).
2. Compare against the cited `evaluation_run_id` pair, or generate a new pair
   and read `relative_improvement` from the new `comparison.json`.
3. Inspect trajectory fixtures under `backend/tests/fixtures/trajectories/`
   and live run JSONL via `GET /runs/{id}/trajectory`.

Do not treat remembered WIS or README percentages as the result. Commands in
README / reproduction docs must stay synchronized with the repo.

---

## 13. Evaluation requirements

**Baseline, agent, and comparison Implemented.**

- Identical cases for baseline and advanced; minimum 12; required phenomena
  including one adversarial case ([evaluation.md](evaluation.md)).
- Primary metric: **WIS**. Secondaries: sMAPE, WMAPE, MASE, coverage, average
  interval width, runtime, cost where measurable, human intervention count.
- Executable scripts only; preserve raw + aggregate artifacts; record failures;
  **do not drop failed cases** from official aggregates.
- No manually entered scores; no hard-coded improvement.

**Current evidence:** `evaluation/results/comparison.json`
(`comparison-20260830T030644Z`). Official WIS `relative_improvement`
**0.13264925035654543**. Do not state that ForecastWize wins every case.

---

## 14. Hackathon deliverables

| Deliverable | Status |
|---|---|
| Defined baseline | **Implemented** (code + `baseline-20260830T020244Z`) |
| Advanced agentic solution | Graph + `POST /runs` + run UI **Implemented** (EXP-010 official) |
| Identical evaluation cases | **Implemented** (`case_lists_identical` true) |
| ≥12 cases + ≥1 adversarial | **Implemented** (001–012; 012 adversarial) |
| Measured improvement (WIS artifacts) | **Measured; 13.26% WIS** (`relative_improvement` 0.1326) |
| Reproducible evaluation | Baseline + agent + compare **Implemented** |
| Agent trajectory logging | Orchestrator + child-agent JSONL **Implemented**; fixtures checked in |
| Improvement changelog | **Implemented** ([changelog.md](changelog.md)); official WIS win claimed only from artifacts |
| Reproduction instructions | **Implemented** |
| Tests | Skeleton + baseline + REST API + backtest + catalog + harness + agent + orchestrator **Implemented** |
| Human checkpoints | Graph + HTTP + UI **Implemented** |

---

## 15. Risks and limitations

**Known now (from artifacts and repo behavior)**

- Official WIS vs baseline improved ~13.26% (`comparison-20260830T030644Z`).
  Case **012** still loses holdout WIS.
- Every agent eval case WARNs and opens a checkpoint (`human_intervention_count` 12 = checkpoints opened, 0 human decisions).
- Optional `OPENAI_API_KEY` is unused; no third-party LLM calls.
- No authentication; API is for a local operator ([security.md](security.md)).
- `make` is not required; Windows uses `.\make.cmd` / `scripts/check.ps1`.
- Official catalog eval defaults `persist_trajectory=True` and writes
  `evaluation/results/trajectories/`. `human_intervention_count` is
  checkpoints opened, not human decisions.

**Expected residual**

- Interval metrics (WIS) can disagree with point metrics; official claim is WIS.
- Short history, intermittency, and adversarial series remain in the catalog
  **so** failure stays visible. On the cited pair, 012 still loses holdout WIS.
- Vendor LLM outage/cost/wording would matter only after an LLM is wired.

Failed experiments and removed approaches are recorded in
[changelog.md](changelog.md) with artifact links. **Removed experiment:
EXP-009** (failed catalog WIS).

**Biggest improvement (official pair):** catalog WIS **13.26%** (EXP-010).

**Biggest failure (official pair):** case 012 still loses holdout WIS; 12
human interventions vs 0.

**Main engineering lesson:** do not let a hypothesis shortlist or a verifier
FAIL change which models are scored or swap to a worse backtest WIS; use
named train-only policies, not silent fill.
