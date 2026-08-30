# Demo script

This script covers **implemented** behavior. Do **not** run a live 12-case
catalog evaluation during the demo. Official scores and trajectories are
already validated and checked in.

## Official result (do not invent)

Source: `evaluation/results/comparison.json` (`comparison-20260830T030644Z`).

| Item | Value |
|---|---|
| Baseline WIS | `0.9153325914744158` (~0.91533) |
| Advanced WIS | `0.7939144093884205` (~0.79391) |
| Relative improvement | `0.13264925035654543` (~**13.26%**) |
| Cases | 12 / 12 completed, 0 failed |
| Holdout | 8 advanced wins, 2 baseline wins, 2 ties |
| Official advanced | EXP-010 (`selection_policy=exp010`, `origin_planning=model_specific`, `R=5.0`) |

The advanced path does **not** win every case. Case **012** remains a
baseline win. Do not claim every metric improved. Deterministic Python
selected the model from backtest and robustness evidence; an LLM did not.

## Human checkpoint vs human decision

| Path | What happened |
|---|---|
| Automated catalog benchmark | 12 checkpoints opened, **0** human decisions |
| Interactive HITL demo | 1 real checkpoint, 1 real `HUMAN_DECISION=accept`, 1 `RUN_COMPLETED` continuation |

`human_intervention_count` counts **checkpoints opened**. Do not say
“12 human decisions.” The checked-in interactive example is
`evaluation/artifacts/human-demo/` — see
[human-in-the-loop-demo.md](human-in-the-loop-demo.md).

## Live path (short)

Use the already-validated catalog **001** interactive path or the
checked-in human-demo artifact. Do not queue a full catalog rerun.

1. Copy `.env.example` to `.env` (leave `OPENAI_API_KEY` empty).
2. Install dependencies: `make setup` (or [docs/reproduction.md](reproduction.md)).
3. Start the API: `python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000` from `backend/`.
4. Open `http://127.0.0.1:8000/health` — expect JSON `status: ok` and header `X-Request-ID`.
5. Start the UI: `npm run dev` from `frontend/`.
6. Open `http://localhost:3000`. Confirm API status is ok, or an **error** with **Retry health check** if the API is down.

## Pitch order

Present these nine points. Numbers come from checked-in artifacts, not a
live 12-case rerun.

### 1. Problem

Analysts need a defensible forecast and interval, not an LLM that invents
MAPE. Deterministic Python owns yhat, intervals, and WIS.

### 2. Baseline

Conventional expanding-window backtest on the shared 12-case catalog
(`python evaluation/run_baseline.py`). Official baseline WIS
**0.9153325914744158**. No LLM. No graph.

### 3. Advanced approach

Explicit graph (`run_orchestrator`). Official selection is **EXP-010**:
model-specific valid backtest origins plus a deterministic last/earlier
fold-WIS veto (`R=5.0`). The LLM/agent does **not** generate yhat or
choose the winner. Generation is a separate `run_baseline_forecast` call.

### 4. 13.26% WIS improvement

Open **Evaluation** (`/evaluation`). BASELINE vs ADVANCED tiles come from
`evaluation/results/comparison.json` via `GET /evaluations/dashboard`.
Official WIS relative improvement **~0.1326**. 12 / 12 completed. Holdout
**8 / 2 / 2**. Do not claim a win on every case.

### 5. Case 012 robustness example

Case **012** (adversarial regime change) still loses holdout WIS to
baseline. EXP-009 had selected ETS at catastrophic holdout WIS; the
EXP-010 veto cut that failure but did not beat baseline on this case.
That honesty is part of the demo.

### 6. Case 005 ARIMA survival

Case **005** (missing values) completes on the official pair. Named
train-only interpolate is applied by the eval harness before the graph;
holdout is never passed in. Open the per-case table; do not invent the
selected model.

### 7. Human checkpoint

Every official catalog case opens a WARN checkpoint. Automated evaluation
records `HUMAN_CHECKPOINT_CREATED` only. It never fabricates a human
click. `human_intervention_count` **12** = checkpoints opened.

### 8. Real Accept decision

Show one real human action, not the catalog count. Either:

- walk Accept on a catalog **001** interactive run, or
- open the checked-in artifact under `evaluation/artifacts/human-demo/`

That artifact has 1 real `HUMAN_DECISION=accept` and a following
`RUN_COMPLETED`. None of Accept / Reject / Review modify the uploaded CSV.

### 9. Trajectory evidence

Official catalog: 12 real JSONL files under
`evaluation/results/trajectories/agent-20260830T030413Z/`.
Fixtures under `backend/tests/fixtures/trajectories/` are tests only.
See [trajectory-evidence.md](trajectory-evidence.md).

Optional UI extras: upload a CSV on **Upload dataset**, start a graph
run, and open forecast / verification screens. Official backtest WIS is
displayed, not calculated in the browser. **Queue a new catalog run**
does not replace the committed JSON dashboard and is **not** the live
demo.

## Not in this demo

- Invented improvement percentages
- A claim that every case or every metric improved
- A claim that an LLM selected the model
- A claim that automated evaluation generated 12 human decisions
- A live full 12-case evaluation rerun
- Authentication
- A vendor LLM call
