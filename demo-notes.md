# ForecastWize Demo Notes

Judge-facing walkthrough for the HackerEarth submission. This document describes **implemented** behavior. Do not treat a planned item as live.

**Related:** [docs/demo-script.md](docs/demo-script.md) (short live path), [docs/human-in-the-loop-demo.md](docs/human-in-the-loop-demo.md) (Accept / Reject / Review), [docs/architecture.md](docs/architecture.md), [docs/forecastwize-architecture.png](docs/forecastwize-architecture.png).

---

## Implemented vs not in this demo

| Area | Status |
|---|---|
| Next.js / TypeScript analyst UI | **Implemented** |
| FastAPI adapters | **Implemented** |
| Typed agent state machine (`run_orchestrator`) | **Implemented** (not a LangGraph library dependency) |
| Data Detective, Context Analyst, Forecast Strategist, Verifier, Forecast Analyst | **Implemented** |
| Deterministic engine: naive, seasonal naive, ETS, ARIMA | **Implemented** (statsmodels / pandas / NumPy) |
| Backtest, WIS, prediction intervals, robustness veto (EXP-010, `R=5`) | **Implemented** |
| Human checkpoint: labeled Accept / Reject / Review | **Implemented** |
| Official 12-case WIS comparison | **Implemented** (checked-in JSON; do not rerun live) |
| Vendor LLM / OpenAI call | **Not integrated** — leave `OPENAI_API_KEY` empty |
| scikit-learn / LightGBM / XGBoost | **Not in the running engine** (optional ML only if eval later justifies it) |
| Excel upload | **Not implemented** (CSV only: `timestamp`, `value`) |
| Authentication / production database | **Not started** / **not used** |

---

## 1. Demo Objective

By the end of the demo, a judge should be able to state:

1. ForecastWize is **decision support for demand/sales-style forecasting**, not a chatbot that emits MAPE.
2. **Agents reason**; **deterministic Python owns yhat, intervals, and metrics.** An LLM does not invent the forecast.
3. The live UI shows diagnosis → strategy → forecast → verification → human gate → explanation.
4. Quality is measured: official **WIS** on **12 identical cases** vs a conventional baseline improved **~13.26%**, and the advanced path **does not win every case**.
5. Weak or uncertain results are **challenged** (verifier PASS / WARN / FAIL) and can stop for an **explicit human checkpoint**. Nothing is auto-approved.

---

## 2. Demo Duration

Recommended **6 minutes** (range 5–7). Do **not** queue a live 12-case catalog rerun.

| Block | Time | What you show |
|---|---|---|
| Introduction | ~30s | Product one-liner + core split (agents vs Python) |
| Problem | ~30s | Analyst must defend a number used for stock/staffing |
| Data upload | ~40s | CSV ingest and validation |
| AI diagnosis | ~40s | Diagnostics + Data Detective on the agent pipeline |
| Forecast strategy | ~30s | Strategist hypothesis; backtest still owns the winner |
| Forecast generation | ~35s | Pipeline: BACKTEST → FORECAST (numbers from the engine) |
| Verification | ~30s | PASS / WARN / FAIL checks |
| Challenge / re-evaluation | ~25s | Explain FAIL→retry (bounded) **and** live WARN→human gate |
| Final forecast | ~30s | Chart, intervals, selected model (API values) |
| Explanation and insights | ~35s | Evidence-cited narrative; no invented promotions |
| Architecture / measured result | ~40s | Layer diagram + Evaluation dashboard (official WIS) |
| Closing | ~20s | Trustworthy procedure, not chat |

If time is tight, cut architecture talk and keep Evaluation (the measured claim). If the live run is slow, skip upload and open the last session run plus Evaluation.

---

## 3. Demo Scenario

### Business problem

A demand analyst must produce a **14-day** daily forecast of units for a product-like series so operations can plan replenishment. They need a point forecast, an interval, a reason the method was chosen, and a clear stop if evidence is weak.

### Dataset (**Implemented** catalog series, not a customer extract)

Use evaluation case **001** (`trend`): smooth daily series with a visible upward trend and low noise.

| Field | Value |
|---|---|
| File | `data/evaluation/001_trend.csv` |
| Framing | Daily product demand analogue (synthetic catalog series) |
| Frequency | `D` |
| Training length | **180** rows (`history_length`) |
| Horizon | **14** steps |
| Seed | **1001** |
| Coverage | **0.95** (configure form default) |

**Leakage rule:** the catalog CSV is train + holdout concatenated. For the **UI demo**, upload **header + first 180 data rows only**. Do not upload the holdout tail. Official scores are **not** computed from this UI run; they come from `evaluation/results/comparison.json`.

PowerShell (repo root), header + 180 rows:

```powershell
Get-Content data\evaluation\001_trend.csv -TotalCount 181 | Set-Content -Encoding utf8 demo-001-train.csv
```

Then upload `demo-001-train.csv`.

### Forecasting objective

Generate a 14-step daily point forecast and prediction intervals from **training history only**. Select among `naive`, `seasonal_naive`, `ets`, `arima` using **official backtest WIS** and the EXP-010 robustness veto. Verify, then wait for a human if WARN/FAIL remains.

### What the analyst wants to know

- Is the history usable (gaps, outliers, frequency)?
- Which method won on **backtest evidence**, not a prompt?
- How wide is the interval, and did verification challenge it?
- What should I **Accept / Reject / Review**?
- What is still uncertain?

Do **not** quote a live-run MAPE or WIS as the official result. If you need the measured claim, use the Evaluation screen.

**Official catalog (not this single UI run):** baseline WIS `0.9153325914744158`, advanced WIS `0.7939144093884205`, relative improvement `0.13264925035654543` (~13.26%), `comparison-20260830T030644Z`. Case **001** is the largest per-case holdout WIS gain on that pair (`relative_improvement` ~0.894). Case **012** still loses to baseline. Do not claim every case or every secondary metric improved.

---

## 4. Step-by-Step Demo Flow

**Before you start**

1. Copy `.env.example` to `.env`. Leave `OPENAI_API_KEY` empty.
2. `make setup` (or [docs/reproduction.md](docs/reproduction.md)).
3. API: from `backend/`, `python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000`.
4. UI: from `frontend/`, `npm run dev` → `http://localhost:3000`.
5. Confirm `/health` is `status: ok` (dashboard Health card).
6. Have Evaluation (`/evaluation`) ready in a second tab. Do not click **Queue a new catalog run**.

### 1. Upload dataset

| | |
|---|---|
| **Presenter does** | Dashboard → **Upload dataset**. Choose `demo-001-train.csv`. |
| **UI** | `/upload`. Typed errors if the file is invalid. On success, redirect to diagnostics. |
| **Agent** | None yet (API ingest). |
| **Deterministic** | Upload validation: type, size, CSV columns, path safety. Original file stored; missing values recorded, not filled. |
| **Say** | “The file is parsed as data only. We never execute uploads. Holdout is not in this file.” |

### 2. Data profiling

| | |
|---|---|
| **Presenter does** | Stay on **Dataset diagnostics**. Point at row count, range, frequency, missing counts. |
| **UI** | `/datasets/{id}`. Cards from the API (not browser math). |
| **Agent** | Orchestrator **PROFILE** node (after you start a run). Upload-time profile is already on this page. |
| **Deterministic** | `inspect_series` / dataset diagnostics in `backend/app/data/`. |
| **Say** | “Profiling is Python. The UI only displays it.” |

### 3. Data Detective findings

| | |
|---|---|
| **Presenter does** | Note Anomalies / Seasonality / Structural break cards. Then **Configure** → horizon `14`, frequency `D`, coverage `0.95`, seed `1001` → start run. Watch **Agent run**. |
| **UI** | Diagnostic flags on the dataset page. Pipeline step **Data Detective** on `/runs/{id}`. |
| **Agent** | **Data Detective** (`DIAGNOSE`). |
| **Deterministic** | `diagnose_quality`, `diagnose_outliers`, `diagnose_trend`, `diagnose_seasonality`, `diagnose_structural_breaks`, etc. No yhat. |
| **Say** | “The detective cites tool evidence. It does not rewrite the CSV.” |

### 4. Forecast strategy selection

| | |
|---|---|
| **Presenter does** | Point at **Forecast Strategy** on the pipeline, then later **Model comparison**. |
| **UI** | Pipeline + `/runs/{id}/comparison` (WIS ranks, veto / selectable flags when the API returns them). |
| **Agent** | **Forecast Strategist**. Shortlist is a **hypothesis**. |
| **Deterministic** | `evaluate_candidates`, expanding-origin backtest, EXP-010 last/earlier fold-WIS veto (`R=5`). Winner = official backtest WIS among models that pass. |
| **Say** | “The agent does not pick the winner by vibe. Python scores the allow-list. Optional ML is not in this build.” |

### 5. Context analysis

| | |
|---|---|
| **Presenter does** | Point at **Context Analysis** on the pipeline. Case 001 has no `context` / `event` columns. |
| **UI** | Pipeline step completes. Analyst narrative will say context is unavailable if none was provided. |
| **Agent** | **Context Analyst**. |
| **Deterministic** | `inspect_context`. Does not invent holidays or promotions. |
| **Say** | “No context in the file means ‘unavailable,’ not a made-up campaign story.” |

### 6. Candidate model evaluation

| | |
|---|---|
| **Presenter does** | Open **Model comparison**. Lower WIS is better. |
| **UI** | `/runs/{id}/comparison`. If `candidates` is empty, say so — do not invent rows. |
| **Agent** | Strategist requested the tool; it does not compute WIS. |
| **Deterministic** | Full allow-list backtest (`naive`, `seasonal_naive`, `ets`, `arima`), robustness flags. |
| **Say** | “Completed-only WIS is labeled and is not the selection rule.” |

### 7. Forecast generation

| | |
|---|---|
| **Presenter does** | Wait for **Forecast** on the pipeline. Open **Forecast result**. |
| **UI** | Chart: history, yhat, interval band (API series). Model, training range, horizon, seed, `generated_at`. |
| **Agent** | Orchestrator **FORECAST** node requests a tool. |
| **Deterministic** | `run_baseline_forecast` for the selected `strategy_id`. |
| **Say** | “These numbers came from the fitter. The browser does not calculate WIS.” |

### 8. Forecast verification

| | |
|---|---|
| **Presenter does** | Open **Verification**. Catalog-style runs typically overall **WARN** (not a silent pass). |
| **UI** | `/runs/{id}/verification`. Per-check PASS / WARN / FAIL from the API. |
| **Agent** | **Forecast Verifier** (interprets tool output; cannot quietly override a FAIL). |
| **Deterministic** | `verify_forecast`: bounds, range, trend, seasonality, residuals, coverage, width, regime, invalid values. |
| **Say** | “The verifier challenges the forecast. WARN is not auto-accept.” |

### 9. Challenge / re-evaluation if needed

| | |
|---|---|
| **Presenter does** | Show the **human checkpoint** panel. Explain the two paths. Click **Accept** once (real decision). |
| **UI** | Accept / Reject / Review. Status `waiting_for_approval` until Accept or Reject. |
| **Agent** | Orchestrator **RETRY_OR_ACCEPT**. Max retries = **2**. |
| **Deterministic** | FAIL retries **only** if an untried selectable model has **strictly better** official backtest WIS. Otherwise escalate. |
| **Say** | “Official 12-case JSONL recorded **0** forecast retries. What you see live is the WARN gate. Exhaustion never auto-approves. Accept does not modify the CSV.” |

Do not wait for a FAIL retry on case 001. If it does not happen, that is expected.

### 10. Final forecast

| | |
|---|---|
| **Presenter does** | After Accept, stay on **Forecast result**. Point at yhat, interval, selected model. |
| **UI** | Summary, chart, KPIs copied from the forecast artifact. |
| **Agent** | Does not rewrite yhat on Accept. |
| **Deterministic** | Same artifact produced at FORECAST. |
| **Say** | “Human governance of the recommendation — not a new invented series.” |

### 11. Explanation

| | |
|---|---|
| **Presenter does** | Scroll to **Final analysis**, **Evidence**, **Risks**. |
| **UI** | Evidence IDs; twelve-section analyst narrative from the API. |
| **Agent** | **Forecast Analyst**. Repeats numbers only with evidence. |
| **Deterministic** | Tool results already stored; analyst does not recompute WIS. |
| **Say** | “Every material number should trace to an evidence ID in the trajectory.” |

### 12. Actionable business insights

| | |
|---|---|
| **Presenter does** | Read uncertainty, risks, and what a human should watch. Do not invent replenishment quantities. |
| **UI** | Analyst sections + Decision readiness. |
| **Agent** | Forecast Analyst — bounded; does not invent events or ERP actions. |
| **Deterministic** | Interval width, coverage, verification flags inform the narrative. |
| **Say** | “Insights are ‘what the evidence supports,’ not a made-up buy list.” |

Then switch to **Evaluation** (`/evaluation`): BASELINE vs ADVANCED tiles from `GET /evaluations/dashboard` (checked-in JSON). Mention 8 / 2 / 2 holdout outcomes and case **012**.

---

## 5. Key Screens to Demonstrate

| Screen | Route | Why it matters |
|---|---|---|
| Dashboard | `/` | Health, journey, “UI does not calculate official WIS.” |
| Upload | `/upload` | Validated CSV ingest; failures are visible. |
| Dataset diagnostics | `/datasets/{id}` | Data quality before any model. |
| Configure | `/datasets/{id}/configure` | Horizon / frequency / seed; **does not** pick the winning model. Frozen EXP-010 note. |
| Agent run | `/runs/{id}` | Typed pipeline + live status + checkpoint. |
| Forecast result | `/runs/{id}/result` | Chart, intervals, governance, evidence, analyst text. |
| Verification | `/runs/{id}/verification` | Challenge results, not a summary of yhat. |
| Model comparison | `/runs/{id}/comparison` | Backtest WIS ranks / veto flags from the API. |
| Evaluation | `/evaluation` | Official measured improvement. Do not rerun the catalog. |
| Changelog (optional) | `/evaluation/changelog` | Honest experiment history if a judge asks. |

Architecture PNG for the talk track: `docs/forecastwize-architecture.png`.

---

## 6. Agentic AI Demonstration

This is **not** “paste a CSV into ChatGPT.” Show:

| Mechanism | What to point at |
|---|---|
| Specialized agents | Pipeline labels: Detective, Context, Strategist, Verifier, Analyst + Orchestrator |
| Orchestration | Named nodes: PROFILE → DIAGNOSE → CONTEXT → STRATEGY → BACKTEST → FORECAST → VERIFY → RETRY_OR_ACCEPT → ANALYZE → FINALIZE |
| Typed / shared state | Run payload: `nodes_visited`, `selected_strategy_id`, `evidence_ids`, verification overall |
| Evidence-based decisions | Evidence list on Forecast result; trajectory JSONL |
| Tool calling | Allow-listed tools only; unknown names rejected |
| Validation gates | Verifier PASS / WARN / FAIL; human checkpoint never auto-approves |
| Challenge / re-evaluation | FAIL + better WIS → bounded retry; else human. Official catalog: **0** retries, **12** checkpoints opened, **0** human decisions |
| Reasoning vs numbers | Strategist hypothesizes; backtest + `run_baseline_forecast` compute |
| Audit trail | `GET /runs/{id}/trajectory`; catalog JSONL under `evaluation/results/trajectories/agent-20260830T030413Z/` |

**Do not say:** “The LLM selected ARIMA.” Deterministic Python selected from backtest / robustness evidence.

---

## 7. Technical Architecture Talking Points

Use this as a ~40s script (with the PNG or Evaluation in view):

> The UI is **Next.js and TypeScript**. It displays backend artifacts. It does not compute official WIS in the browser.
>
> The API is **FastAPI**. Handlers validate input, call domain functions, and return typed models. Forecast math is not in the route.
>
> **Python** owns the engine: pandas, NumPy, statsmodels, Pydantic. Four interchangeable models. Expanding-origin **backtest** on training data. **WIS** is primary; sMAPE and coverage are secondaries. **Prediction intervals** are scored separately from the point forecast.
>
> Agents run in an explicit **typed state machine** (`run_orchestrator`), not a hidden chat loop. They request allow-listed tools. **EXP-010** selection uses model-specific valid origins and a last-to-earlier WIS veto (`R=5`). Generation is a separate fit call.
>
> Uploads are validated. Transforms are named. Source CSV is not overwritten. Trajectory JSONL is append-only: who decided, which tool, which evidence IDs, retry index.
>
> Official proof is the **same 12 cases** for baseline and advanced: `evaluation/results/comparison.json`, about **13.26%** WIS improvement, with losses called out.

---

## 8. Strong Judge Questions and Answers

**Why agents instead of a traditional pipeline?**  
A pipeline can fit models. Analysts also need diagnosis, a challenged result, a stop for humans, and an evidence-cited explanation. Agents coordinate that. They do not replace the fitter.

**How do you prevent hallucinated forecasts?**  
Agents cannot emit authoritative yhat, WIS, or intervals. Only deterministic tools produce those. The verifier rejects unverified claims. No vendor LLM is wired.

**How is model selection performed?**  
Hypothesis shortlist, then execute the full allow-list backtest. Official advanced path: EXP-010 veto, then lowest official backtest WIS among selectable models. The LLM does not apply the veto.

**How do you measure forecast quality?**  
Primary: **WIS** (lower is better) on the full shared catalog. Secondaries always recorded: sMAPE, WMAPE, MASE, coverage, interval width, runtime, checkpoints opened. Headline is WIS, not a prettier secondary.

**How do you handle anomalies?**  
Detect and record (Data Detective / diagnostic tools). No silent clip or drop of the original file. Eval missing values use a **named train-only** interpolate; holdout is not filled.

**How do you handle insufficient or poor-quality data?**  
Diagnostics flag gaps, short history, frequency issues. Verifier can WARN or FAIL. Human checkpoint on material uncertainty. The system fails visibly rather than inventing history.

**How do agents interact with deterministic tools?**  
Typed tool request → allow-list execution → typed result + evidence ID → agent cites the ID. Unknown tools are not executed.

**How is the system reproducible?**  
Pinned dependencies, fixed case seeds, shared catalog, committed `evaluation_run_id`s. See [docs/reproduction.md](docs/reproduction.md). Re-running eval **overwrites** `evaluation/results/*.json` and mints a new id — that is why we demo the checked-in pair.

**How would this scale to production?**  
**Planned / not in this build:** authentication, multi-tenant isolation, a production database. Today: file store under `data/api/`, bind localhost. Scaling would keep the same split: agents orchestrate, Python computes.

**How would you add more forecasting models?**  
Implement the **same** model interface. Add to the allow-list. Promote only if shared-catalog WIS (and honesty about losses) justifies it. Optional ML is explicitly gated on evaluation evidence.

**How would you handle external business context?**  
Optional `context` / `event` columns exist. Context Analyst records labels vs hypotheses and will not invent events. Causal adjustment of yhat from a prompt is **not** implemented.

**What makes this different from asking ChatGPT for a forecast?**  
ChatGPT can invent a number. ForecastWize will not accept a number that did not come from a tool. Same cases as baseline, logged trajectory, verifier challenge, human gate, measured WIS.

---

## 9. 60-Second Elevator Pitch

ForecastWize helps operations analysts produce a demand forecast they can **defend**. The problem is not more chat — it is trustworthy procedure: pick a method, avoid leakage, score intervals, and stop when evidence is weak.

We split the system on purpose. **Agents** profile the series, hypothesize a strategy, challenge the result, and explain it. **Deterministic Python** fits the models, writes yhat and prediction intervals, backtests, and computes WIS. An LLM is not allowed to invent the forecast. There is no vendor LLM in this submission.

On the **same twelve evaluation cases** as a conventional expanding-window baseline, the official advanced path — EXP-010 robust selection — improved aggregate WIS by about **13.26%**. It does **not** win every case; we show the loss on the adversarial series.

In the product, verification can WARN or FAIL, retries are bounded, and a human must **Accept, Reject, or Review**. That is agentic decision support with a statistical engine — not a wrapper around a paragraph of numbers.

---

## 10. 30-Second Closing

ForecastWize is built so a number used for inventory or staffing can be **audited**. Agents reason over evidence; Python computes the forecast, the intervals, and the scores. A verifier **challenges** weak results. A human gate stays explicit. The explanation cites evidence, not authority. If you remember one thing: **trustworthy forecasting is agentic reasoning plus deterministic computation, measured on the same cases as the baseline.**

---

## 11. Demo Safety / Fallback Plan

| If this happens | Do this |
|---|---|
| Health check fails / API down | Show the error on the dashboard (honest). Switch to Evaluation JSON in the UI if the eval endpoint is up, or open `evaluation/results/comparison.json` and `docs/forecastwize-architecture.png`. |
| Upload rejected | Read the typed error. Use the 180-row train slice, columns `timestamp,value`. Do not improvise Excel. |
| Graph is slow | Narrate the pipeline while it runs. Pre-open Evaluation. If needed, **Open last agent run** from the dashboard. |
| `candidates` table empty | Say the API returned no comparison rows for this run. Show Evaluation per-case table instead. Do not type fake WIS. |
| No FAIL retry | Expected. Show WARN + checkpoint. Describe FAIL→retry as implemented control flow (max 2), not a live event on this series. |
| Checkpoint already accepted | Walk the recorded decision and evidence. Optional checked-in HITL artifact: `evaluation/artifacts/human-demo/run_f4c8529410f148e8a6f4973abf3440ee/`. |
| Judge asks for 12-case live rerun | Decline. Official pair is checked in. Rerun overwrites results and is not the demo. |
| Judge asks ChatGPT to “just give MAPE” | Contrast: we refuse invented metrics; tools + comparison.json only. |
| Wrong seed/horizon | Reconfigure; do not claim the live run is the official scorecard. |

**Never:** invent improvement percentages, claim every case won, claim 12 human *decisions* (that is 12 checkpoints **opened**), claim an LLM chose the model, or present authentication as shipped.

---

## 12. Final Judge Takeaways

- **Agents reason; Python forecasts.** No invented yhat, WIS, or intervals.
- **Same 12 cases** as baseline; official WIS improved **~13.26%** (`comparison-20260830T030644Z`), with **losses disclosed** (including case 012).
- **Verifier + human checkpoint:** challenge, bounded retry, explicit Accept / Reject / Review — never auto-approve.
- **Traceable:** append-only trajectory, evidence IDs, frozen EXP-010 selection (`R=5`).
- **Built for analysts:** diagnosis, intervals, explanation, and a defensible number — not a chatbot forecast.
