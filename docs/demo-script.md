# Demo script

This script covers **implemented** behavior. It does **not** claim a WIS win.
Official catalog scores are in `evaluation/results/comparison.json`
(`comparison-20260829T125254Z`): WIS `relative_improvement` **0.0**; agent
`human_intervention_count` **12**.

1. Copy `.env.example` to `.env` (leave `OPENAI_API_KEY` empty).
2. Install dependencies: `make setup` (or [docs/reproduction.md](reproduction.md)).
3. Start the API: `python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000` from `backend/`.
4. Open `http://127.0.0.1:8000/health` — expect JSON `status: ok` and header `X-Request-ID`.
5. Start the UI: `npm run dev` from `frontend/`.
6. Open `http://localhost:3000`. Confirm API status is ok, or an **error** with **Retry health check** if the API is down.
7. Upload a CSV (`timestamp`, `value`) from **Upload dataset**. Expect a diagnostics screen with row count, date range, frequency, missing periods, anomalies, seasonality, and structural break — values from the API.
8. Configure horizon/frequency/coverage/seed and start the agent graph. The execution screen should list Data Detective → Forecast Strategist → Context Analyst → Backtesting → Forecast → Verification → Final Analysis.
9. Open forecast result: historical series, point forecast, and interval come from the API. Warnings (WARN) are visually distinct from failures (FAIL / request errors).
10. Open verification and model comparison. Official backtest WIS is displayed, not calculated in the browser.
11. Open **Evaluation** (`/evaluation`). BASELINE vs ADVANCED tiles, per-case table, challenging case 012, won/lost lists, and official WIS improvement come from `evaluation/results/comparison.json` via `GET /evaluations/dashboard`. Expect **0.0** official WIS relative improvement and **12** agent human interventions on the cited pair. Negative and null results stay visible. Open **Experiment changelog** for `docs/changelog.md`.
12. Optional: **Queue a new catalog run** at `/evaluations`. That does not replace the committed JSON dashboard.
13. If the run waits for approval, use **Accept**, **Reject**, or **Review** on the execution, result, or verification screen. Reject keeps the decision on the trajectory (`GET /runs/{id}/trajectory`). None of these actions modify the uploaded CSV.
14. Optional: open a checked-in trajectory fixture
    `backend/tests/fixtures/trajectories/successful_run.jsonl` to show
    append-only steps (`tool_invocation` → `decision` → `final_status`).

## Not in this demo

- Invented improvement percentages
- A claim that the agent beats baseline on WIS
- Authentication
- A vendor LLM call
