# Agent design

## Implemented

- Deterministic `backtest` tool (`backend/app/tools/backtest_tools.py`):
  `origin_planning='shared'` calls `run_rolling_origin_backtest` (baseline
  and historical EXP-008). Official advanced EXP-010 uses
  `origin_planning='model_specific'` → `run_model_specific_origin_backtest`.
  Bare `--origin-planning model_specific` still reproduces EXP-009 (no veto).
  Unknown tool names and model ids are rejected.
- Deterministic **data diagnostic tools** (`backend/app/tools/data_tools.py`):
  `inspect_series`, `diagnose_quality`, `diagnose_outliers`,
  `diagnose_rolling_anomalies`, `diagnose_trend`, `diagnose_seasonality`,
  `diagnose_structural_breaks`. Unknown names are rejected. No yhat. No in-place
  edits.
- Deterministic **forecast evaluation** (`evaluate_candidates` /
  `list_supported_models` in `backend/app/tools/forecasting_tools.py`).
  Compact official WIS snapshots; no production yhat.
- Deterministic **robustness analysis** (`analyze_backtest_robustness` in
  `backend/app/tools/robustness_tools.py`): last/earlier fold-WIS veto
  (`R=5`) when `selection_policy='exp010'` (official advanced default).
  No holdout. No yhat. The LLM does not compute or apply the veto.
- Deterministic **context inspection** (`inspect_context` in
  `backend/app/tools/context_tools.py`). Records optional event/context labels;
  does not invent events or infer causes.
- **Data Detective** (`backend/app/agents/data_detective.py`): explicit
  sequential state (not LangGraph). Calls only diagnostic tools, cites evidence
  IDs, labels hypotheses, exposes uncertainty, writes append-only trajectory
  JSONL. Does not forecast, invent events, or modify data.
- **Forecast Strategist** (`backend/app/agents/forecast_strategist.py`):
  inspects structured diagnostics, proposes candidates as hypotheses, requests
  `evaluate_candidates`, and recommends `strategy_id` from official
  backtest WIS among models that pass the EXP-010 instability veto
  (official default). Historical shared-origin ranking remains
  `selection_policy='default'`. No superiority claim without executed
  backtesting. The strategist does not emit yhat.
- **Context Analyst** (`backend/app/agents/context_analyst.py`): optional
  event/context labels (promotion, holiday, campaign, price change, stockout,
  product launch, external business event). Observed facts vs possible
  explanations. No causal claims. If no context data exists, the report states
  that contextual analysis is unavailable. Does not adjust forecasts.
- Deterministic **forecast verification** (`verify_forecast` in
  `backend/app/tools/verification_tools.py`) plus **Verifier**
  (`backend/app/agents/verifier.py`): PASS/WARN/FAIL checks (bounds, range,
  trend, seasonality, residuals, coverage, interval width, regime-change,
  extreme growth, invalid values). Interpretation cannot change a
  deterministic result without a recorded override reason.
- **Forecast Analyst** (`backend/app/agents/analyst.py`): twelve-section
  evidence-cited narrative over a verified forecast. Repeats yhat/intervals
  from the artifact; does not invent business recommendations or events.
- **Orchestrator** (`backend/app/agents/orchestrator.py`): explicit typed
  state machine (not a graph library). Nodes: START → PROFILE → DIAGNOSE →
  CONTEXT → STRATEGY → BACKTEST → FORECAST → VERIFY → RETRY_OR_ACCEPT →
  ANALYZE → FINALIZE. Max retries = 2. Verification is required before an
  accepted result. FAIL retries only when an untried model has **strictly
  better** official backtest WIS than the current selection. PASS
  proceeds to the analyst and can complete. WARN proceeds to the analyst
  then waits for a human checkpoint. Exhaustion of FAIL retries (or FAIL
  with no better-WIS alternative) returns `waiting_for_approval` (never
  auto-approved). Failures are preserved. BACKTEST executes the caller
  allow-list (`BASELINE_MODEL_IDS` in evaluation), not the strategy
  shortlist; the shortlist is a hypothesis only.
  Trajectory is append-only JSONL.
- Explicit **human checkpoints** (`backend/app/agents/checkpoint.py`):
  required for proposed data modification, low forecast confidence,
  repeated verification failure, and remaining material uncertainty.
  `POST /runs/{id}/checkpoint` records Accept, Reject, or Review. Rejected
  decisions are appended to the run trajectory. Source CSV is never modified.
  The graph never auto-approves. The UI shows labeled Accept / Reject / Review
  controls (`HumanCheckpointPanel`).
- Trajectory fields: `run_id`, `agent_id`, `timestamp`, `agent_instruction`,
  `input_state_hash`, `input_summary`, `tool_invocation`, `tool_output_ref`,
  `decision`, `evidence_ids`, `retry_number`, `status`, `next_step`, `error`,
  `final_result`. Writer: `backend/app/evidence/`. Representative fixtures:
  `backend/tests/fixtures/trajectories/`.

Live API runs write `{run_id}.jsonl` under the file store (`data/api/` by
default). Official catalog `run_agent.py` defaults `persist_trajectory=True`
and writes one JSONL per case under `evaluation/results/trajectories/`.
Child agents append to that same file. See
[docs/trajectory-evidence.md](trajectory-evidence.md).
Evaluation `human_intervention_count` is checkpoints opened, not human
decisions.

## Evaluation (do not invent scores)

The graph is the advanced path in `python evaluation/run_agent.py` (official
default `selection_policy='exp010'`). Official WIS vs baseline is **only**
`evaluation/results/comparison.json`. Cited pair:
`comparison-20260830T030644Z`, `aggregate.metrics.wis.relative_improvement`
**0.13264925035654543** (~13.26%). Holdout outcomes: 8 advanced wins, 2
baseline wins, 2 ties. EXP-009 isolated pair (`comparison-20260829T154706Z`)
is **not** a WIS win (`relative_improvement` −1.662); reproduce with
`--origin-planning model_specific` (planner only). Frozen EXP-010 isolate:
`evaluation/artifacts/EXP-010-robust-model-selection/`
(`comparison-20260830T014245Z`). WARN on every catalog case produces
`human_intervention_count` 12 (checkpoints opened, not human decisions).
That is a secondary, not a substitute for WIS.

## Planned

Agents remain decision-support only. They must not emit authoritative yhat,
intervals, or metrics. Those come from deterministic Python tools. HTTP
`POST /runs` / `POST /runs/{id}/checkpoint` / `GET /runs/{id}` /
`GET /runs/{id}/trajectory` are **Implemented**.

### Remaining MUST (product wiring)

- Shared allowlist exposed through the API OpenAPI description (tools remain allowlisted in code)

### MAY

- Select candidate strategies, request tools, interpret diagnostics, propose
  transforms, explain selection, identify risks, recommend human review

### Verifier

A graph step that **challenges** the forecast (leakage, residuals, calibration,
missing evidence). Summarizing metrics is non-compliant.

**Implemented (deterministic):** `verify_forecast` + `run_verifier` emit
PASS/WARN/FAIL with check ID, evidence, severity, and explanation. An LLM may
interpret those results only with a recorded override reason. The orchestrator
runs verification after every forecast-fit and will not accept a FAIL. FAIL
retries only on strictly better official backtest WIS. WARN proceeds to the
analyst then `waiting_for_approval`.
