# Trajectory evidence index

Reviewer map from **production agents in code** to **real JSONL** already in
this repository. This folder does not replace the artifacts. It points at them.

Official evaluation is frozen. These notes do not change WIS, EXP-010, `R=5.0`,
catalog cases, or any file under `evaluation/results/`.

## Production agents (from code, not docs)

IDs in `backend/app/agents/state.py`, invoked by `run_orchestrator`:

| ID | Module | Role in the graph |
|---|---|---|
| `orchestrator` | `orchestrator.py` | Explicit state machine. PROFILE → … → FINALIZE. |
| `data_detective` | `data_detective.py` | DIAGNOSE. Diagnostic tools only. No yhat. |
| `context_analyst` | `context_analyst.py` | CONTEXT. Observed labels only. |
| `forecast_strategist` | `forecast_strategist.py` | BACKTEST. Official WIS + EXP-010 veto. No yhat. |
| `verifier` | `verifier.py` | VERIFY. Deterministic challenge. |
| `forecast_analyst` | `analyst.py` | ANALYZE. Evidence-cited narrative. No new numbers. |
| `human` | `checkpoint.py` | Records Accept / Reject / Review. Not called by the catalog harness. |

There is no other production agent ID.

## How to read a JSONL line

Each line is one `TrajectoryRecord`. Follow this order:

1. `agent_instruction` — what the agent is allowed to do
2. `event_type` / `actor` / `agent_id` — who acted
3. `tool_invocation.tool_name` — approved tool, if any
4. `tool_output_ref` — pointer into `artifacts/` (payload is not inlined)
5. `payload` / `decision` — structured action result
6. `next_step` — graph successor when the orchestrator recorded one
7. `status` / `final_result` — step outcome

`event_id` is `{run_id}:{sequence}` (for example `agent-20260830T030413Z-005:29`).
`retry_number` is `0` on every official catalog event.

## Source artifacts (do not regenerate)

| Kind | Path |
|---|---|
| Official catalog (12 cases) | `evaluation/results/trajectories/agent-20260830T030413Z/` |
| Manifest | `evaluation/results/trajectories/agent-20260830T030413Z/manifest.json` |
| Case 005 | `evaluation/results/trajectories/agent-20260830T030413Z/case_005.jsonl` |
| Case 012 | `evaluation/results/trajectories/agent-20260830T030413Z/case_012.jsonl` |
| Interactive HITL demo | `evaluation/artifacts/human-demo/run_f4c8529410f148e8a6f4973abf3440ee/trajectory.jsonl` |

Judge walk-through:

```text
Open case_005.jsonl
→ sort by sequence
→ filter agent_id
→ confirm event_id / event_type / tool_invocation against the table below
```

Same for `case_012.jsonl` and the demo `trajectory.jsonl`.

## Agent index

| Agent | Representative run | Key events | Tools | Outcome | Artifact |
|---|---|---|---|---|---|
| `orchestrator` | Catalog **005**; HITL continuation on demo | `RUN_STARTED` → PROFILE tools → `FORECAST_*` → `RETRY_NOT_REQUIRED` → `HUMAN_CHECKPOINT_CREATED` → `RUN_COMPLETED` | `inspect_series`, `forecast_fit` | Catalog: `waiting_for_approval`. Demo after Accept: `completed` | `case_005.jsonl`; demo `trajectory.jsonl` |
| `data_detective` | Catalog **005** | `AGENT_STARTED` → 7× `TOOL_COMPLETED` → `AGENT_COMPLETED` | `inspect_series`, `diagnose_quality`, `diagnose_outliers`, `diagnose_rolling_anomalies`, `diagnose_trend`, `diagnose_seasonality`, `diagnose_structural_breaks` | `completed`; forecastability `limited` | `case_005.jsonl` seq 3–12 |
| `context_analyst` | Catalog **005** (no labels) and **012** (labels present) | `AGENT_STARTED` → `TOOL_COMPLETED` → `AGENT_COMPLETED` | `inspect_context` | 005: `context_available=false`. 012: `true` | `case_005.jsonl` seq 13–16; `case_012.jsonl` seq 13–16 |
| `forecast_strategist` | Catalog **012** (vetoes); **005** (ARIMA win) | `BACKTEST_COMPLETED` → `ROBUSTNESS_ANALYZED` → `MODEL_ELIGIBLE` / `MODEL_VETOED` → `MODEL_SELECTED` | `list_supported_models`, `evaluate_candidates`, `analyze_backtest_robustness` | 012: `naive`. 005: `arima` | `case_012.jsonl` seq 18–31; `case_005.jsonl` seq 18–31 |
| `verifier` | Catalog **005** | `VERIFICATION_STARTED` → `TOOL_COMPLETED` → `VERIFICATION_COMPLETED` | `verify_forecast` | overall `WARN`; `retry_recommended=false` | `case_005.jsonl` seq 34–37 |
| `forecast_analyst` | Catalog **005** | `AGENT_STARTED` → 6× `AGENT_DECISION` → `AGENT_COMPLETED` | none (no `tool_invocation`) | `completed` narrative from supplied artifacts | `case_005.jsonl` seq 39–47 |
| `human` | Demo `run_f4c8529410f148e8a6f4973abf3440ee` | `HUMAN_DECISION` | none | `accept` | demo `trajectory.jsonl` seq 50 |

Per-agent notes: `orchestrator.md`, `data_detective.md`, `context_analyst.md`,
`forecast_strategist.md`, `verifier.md`, `forecast_analyst.md`, `human.md`.

## Retries (actual)

Official 12-case run `agent-20260830T030413Z`:

| Event | Count |
|---|---|
| `RETRY_REQUESTED` | **0** |
| `RETRY_STARTED` | **0** |
| `RETRY_COMPLETED` | **0** |
| `RETRY_NOT_REQUIRED` | **11** (WARN path; `retry_number=0`) |
| `retry_number` on all 599 events | **0** |

Case **003** is verification `FAIL`. The graph did **not** retry: the untried
alternative `ets` did not have strictly better official backtest WIS than
`arima`. Event `agent-20260830T030413Z-003:38` is `HUMAN_CHECKPOINT_CREATED`,
not `RETRY_REQUESTED`.

The interactive demo also has `retry_number=0` and no `RETRY_REQUESTED`.

Do not treat test fixtures as production retries. The retry cap (`max=2`) is
implemented; it did not fire on the frozen official catalog or the checked-in
demo.

## Human checkpoints (actual)

| Path | `HUMAN_CHECKPOINT_CREATED` | `HUMAN_DECISION` |
|---|---|---|
| Official 12-case catalog | **12** (one per case) | **0** |
| Interactive demo `run_f4c8529410f148e8a6f4973abf3440ee` | **1** (seq 48) | **1** = `accept` (seq 50) |

The catalog harness never calls `apply_human_checkpoint`. Checkpoints stay
`waiting_for_approval`. A human decision exists only on the interactive demo.

## Preferred cases

- **005** — missing-value series; EXP-010 selects **arima**; verifier `WARN`;
  checkpoint opened; no retry.
- **012** — adversarial regime change; robustness vetoes seasonal_naive / ets /
  arima; selects **naive**.
- **Demo** — catalog 001 train window; `HUMAN_CHECKPOINT_CREATED` →
  `HUMAN_DECISION` accept → `RUN_COMPLETED` (`continuation_of=HUMAN_DECISION`).

## Requirement coverage

| Hackathon item | Supported by real JSONL? |
|---|---|
| Trajectory for every production agent | **Yes.** Catalog covers six graph agents. `human` is only in the demo (the catalog never invokes it). |
| Instructions → action → tools → responses → next → result | **Yes.** Those fields are on the cited lines. |
| Feedback / checkpoints where they occurred | **Yes.** 12 catalog checkpoints; 1 demo decision. |
| Retries where they occurred | **Yes, as absence.** Zero actual retries. Documented, not invented. |

## Gap (honest)

There is **no official or demo event** of type `RETRY_REQUESTED`,
`RETRY_STARTED`, or `RETRY_COMPLETED`. A judge cannot be shown a live retry
loop from frozen artifacts. Case 003 shows the FAIL-without-swap path instead.
