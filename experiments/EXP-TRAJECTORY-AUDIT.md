# EXP-TRAJECTORY-AUDIT

- **Kind:** audit, then observational persistence implementation
- **Date:** 2026-08-30
- **Scope:** Existing trajectory/evidence path vs official EXP-010 evaluation
- **Forecasting / WIS / cases / baseline:** not changed

## Implementation status (observability phase)

The judge criticism was valid at audit time. Official catalog evaluation now
persists real per-case JSONL. This is observational only.

| Item | After this phase |
|---|---|
| Official `python evaluation/run_agent.py` | `persist_trajectory=True` by default |
| Storage | `evaluation/results/trajectories/<evaluation_run_id>/case_*.jsonl` |
| Child agents | Append to the same case file (`append_to_trajectory=True`) |
| Human decisions | Not fabricated. Eval records `HUMAN_CHECKPOINT_CREATED` only |
| Fixtures | Still fixtures under `backend/tests/fixtures/trajectories/` |
| Forecasting / EXP-010 | Unchanged |

See [docs/trajectory-evidence.md](../docs/trajectory-evidence.md).

**Evaluation `human_intervention_count` represents checkpoints opened, not
human decisions.**

The original audit findings below are **historical**. They describe the
repository **before** official catalog persist was enabled. They are not
the current official trajectory configuration. Current official: 12 real
catalog JSONL files, `persist_trajectory=True` by default. See the table
above and [docs/trajectory-evidence.md](../docs/trajectory-evidence.md).

---

## Historical audit baseline (pre-implementation)

Judge criticism under review: *“Trajectories are partial (schema + thin fixtures, not a full agent+human evaluation trace).”*

**Verdict:** The criticism is **correct**. The schema and logger are real. Official catalog evaluation does **not** persist trajectories. What reviewers can open today is (1) compact `evaluation/results/agent.json` summaries and (2) hand-checked-in fixtures. Those are not a full agent+human evaluation trace.

---

## 1. Then-current trajectory architecture (historical)

Four layers exist. They do not currently compose into a catalog evaluation trace.

| Layer | Location | What it does |
|---|---|---|
| Schema | `backend/app/evidence/trajectory.py` | Typed `TrajectoryRecord` (append-only JSONL line) |
| Logger | `backend/app/evidence/logger.py` | Redact secrets, strip raw series, hash input, write JSONL + artifact refs |
| Artifacts | `backend/app/evidence/artifacts.py` | Write-once `artifacts/{run_id}/A{step}-{sha8}.json` |
| Agents | `backend/app/agents/*.py` | Build `TrajectoryStep` in memory; persist only if a path is provided |

**Orchestrator** (`run_orchestrator`) is the only graph owner of a run file. Child agents (Data Detective, Forecast Strategist, Context Analyst, Verifier, Forecast Analyst) are **always** called with `persist_trajectory=False` from the orchestrator. Their per-tool steps stay in in-memory `state.trajectory` and are discarded when the node returns. The orchestrator then writes **one** step per graph node (if disk persist is on).

**Official evaluation** (`evaluation/run_agent.py`):

```text
persist_trajectory: bool = False
```

`API POST /evaluations/run` also calls `run_agent_evaluation(..., persist_trajectory=False)`.

`API POST /runs` **does** persist (`persist_trajectory=True` under `data/api/trajectories/{run_id}.jsonl`). Those files are gitignored runtime store, not the official 12-case catalog.

**Default persist path** when orchestrator persist is on and no path is passed: `trajectories/{run_id}.jsonl` (gitignored except README).

```text
official eval  ──persist=False──►  no JSONL
                   │
                   └── still runs the graph; agent.json gets compact case rows

API POST /runs ──persist=True───►  orchestrator-node JSONL only
                   │
                   └── child agents still persist=False (inner tools not on disk)

pytest / fixtures ──explicit path──►  schema examples (not catalog cases)
```

---

## 2. Current event/schema model

`TrajectoryStep` (in-memory, `backend/app/agents/state.py`):

`run_id`, `agent_id`, `timestamp`, `input_state`, `tool_requested`, `tool_result`, `decision`, `evidence_ids`, `retry_number`, `final_status`

`TrajectoryRecord` (on disk, `backend/app/evidence/trajectory.py`) adds:

`step_index`, `agent_instruction`, `input_state_hash`, `input_summary`, `tool_invocation` (`tool_name` + `arguments_summary`), `tool_output_ref`, `status`/`final_status`, `next_step`, `error`, `final_result`

There is **no** `case_id`, **no** `event_type` enum, **no** tool start/end timestamps, **no** `event_id`. Sequence is `step_index` (only assigned when writing a file). When `path is None`, `build_record(..., step_index=0)` is used for every step — indexes are not stored on `TrajectoryStep`.

Timestamps on orchestrator/child steps use the **same** `generated_at` for the whole run (eval passes one datetime per catalog batch). Steps are not independently clocked.

`tool_invocation.arguments_summary` is **not** the real tool args. `_args_summary` copies a few keys from the input snapshot (`n_observations`, `frequency`, `horizon`, `node`, `selected_strategy_id`, …).

`tool_result` on the JSONL line is a compact pointer (`ok`, `error_type`, `artifact_id`). Full payloads live in artifacts **only if** a path was provided.

Reviewer walk advertised in `trajectories/README.md`:

`agent_instruction` → `input_summary` → `tool_invocation` → `tool_output_ref` → `decision` → `next_step` → `final_result`

That walk is implemented. It is not populated for official evaluation.

---

## 3. Actual vs fixture coverage

| Source | Origin | Catalog cases? | Agents covered | Human decision? |
|---|---|---|---|---|
| `evaluation/results/agent.json` (`agent-20260830T020331Z`) | **Real** EXP-010 eval | All 12 | Outcomes only | No |
| `evaluation/results/comparison.json` | **Real** compare | All 12 | None | `review_required=true` only |
| `backend/tests/fixtures/trajectories/successful_run.jsonl` | **Fixture** (fixed `2021-03-01`, `run_id=fixture-success`) | No | Data Detective, 3 thin steps | No |
| `verification_retry.jsonl` | **Fixture** (`fixture-retry`) | No | Orchestrator slice: VERIFY → retry → VERIFY → accept → FINALIZE | No |
| `tool_failure.jsonl` | **Fixture** (`fixture-tool-fail`) | No | Orchestrator PROFILE fail + FINALIZE | No |
| `trajectories/data_detective_test.jsonl` | **Pytest leftover** (real detective call, synthetic series) | No | Data Detective only | No |
| `API data/api/trajectories/` | Real interactive runs if someone used the UI | Not the catalog | Orchestrator nodes only | Yes, if `/checkpoint` was called |

Fixtures are **not** live evaluation traces. `backend/tests/fixtures/trajectories/README.md` says they are generated by the logger and “not live runs.” `run_id` values (`fixture-success`, `fixture-retry`, `fixture-tool-fail`) and a frozen `2021-03-01T00:00:00Z` timestamp confirm that.

**Classification of the official catalog pair: B is what reviewers get for JSONL; A exists only as compact evaluation JSON.**

---

## 4. 12-case coverage

Official pair: `evaluation/results/agent.json` / `comparison.json`.

| Question | Answer |
|---|---|
| Cases that **ran** the graph | **12 / 12** (`n_cases_failed = 0`) |
| Cases with a persisted trajectory JSONL | **0 / 12** |
| Cases with a **complete** reviewable trajectory | **0 / 12** |
| Cases with a **partial** outcome row in `agent.json` | **12 / 12** |
| Cases with **no** trajectory file | **12 / 12** |

`evaluation/artifacts/` (EXP-006–010, pre-promotion) also have no `*.jsonl`. Catalog eval has always used `persist_trajectory=False`.

Per-case `agent.json` **does** record, from the real run:

- `case_id`, selected model, `selection_rule`, backtest snapshots (WIS, folds, veto, ratio)
- holdout metrics, `yhat` / intervals
- `retry_number` (all **0**)
- `verification_overall` (11× WARN, case **003** FAIL)
- `human_checkpoint_status` = `waiting_for_approval` on all 12
- `review_required` = true on all 12

That is a **scorecard**, not a trajectory.

---

## 5. Agent coverage

Implemented agents (do not invent others):

| Agent | Official eval JSONL | Official `agent.json` | In-memory during eval | Fixture JSONL |
|---|---|---|---|---|
| Orchestrator | Missing | Implicit (`workflow: run_orchestrator`) | Yes, discarded | Partial slices |
| Data Detective | Missing | Missing | Yes, discarded | Thin / pytest |
| Forecast Strategist | Missing | Compact `backtest[]` + selection | Yes, discarded | Missing |
| Context Analyst | Missing | Missing | Yes, discarded | Missing |
| Verifier | Missing | `verification_overall` only | Yes, discarded | VERIFY slice in retry fixture |
| Forecast Analyst | Missing | Missing | Yes, discarded | Missing |
| Human | Missing | Status only (`waiting_for_approval`) | Checkpoint object, no decision | API tests only |

Even a **live API** orchestrator JSONL would list `agent_id=orchestrator` on every line. Child `agent_id`s would not appear unless those agents persist to the same file.

---

## 6. Tool coverage

Tools that actually run on the official path (deterministic; no LLM):

| Tool / wrapper | Recorded on official eval JSONL | Recorded in `agent.json` |
|---|---|---|
| `inspect_series` | Missing | Missing |
| Detective diagnostics (quality, outliers, rolling, trend, seasonality, breaks) | Missing | Missing |
| `inspect_context` | Missing | Missing |
| `list_supported_models` / `evaluate_candidates` | Missing | Compact backtest rows |
| `analyze_backtest_robustness` | Missing | `vetoed`, `veto_reason`, `selectable`, `recent_vs_earlier_ratio` |
| `forecast_fit` / `run_baseline_forecast` | Missing | `yhat` / intervals / model id |
| `verify_forecast` | Missing | `verification_overall` |
| Analyst (no numeric tool) | Missing | Missing |

If persist were enabled **as coded today**, one orchestrator line per node would record `tool_requested` as e.g. `inspect_series`, `run_data_detective`, `inspect_context`, `evaluate_candidates`, `forecast_fit`, `verify_forecast`. Inner detective/strategist/robustness/verifier check tools would still be **absent** from the file.

Tool-trace fields vs the requirement:

| Field | Official eval | If persist=True (current code) |
|---|---|---|
| Tool name | Missing | Partial (node wrapper name) |
| Arguments / safe summary | Missing | Thin snapshot keys, not real args |
| Start timestamp | Missing | Same `generated_at` as every other step |
| End timestamp | Missing | Missing |
| Result | Partial (backtest/forecast arrays) | Compact + artifact if path set |
| Failure | Partial (`error_type` on failed cases only; none failed) | `error` on failed steps |
| Evidence ID | Missing | Yes on orchestrator steps |
| Agent requesting | Missing | Always `orchestrator` |
| Workflow step | Missing | `input_summary.node` |

---

## 7. Verification coverage

**Real execution:** `verify_forecast` ran for all 12 cases.

| Case | `verification_overall` | In trajectory file | Check-level results |
|---|---|---|---|
| 001, 002, 004–012 | WARN | No | No |
| 003 | FAIL | No | No |

`agent.json` stores only the overall string. Individual verifier challenges (bounds, residuals, coverage, regime, …) are not in the official artifacts.

The retry fixture shows VERIFY FAIL then VERIFY PASS — **not** catalog case 003.

---

## 8. Retry coverage

Official EXP-010 agent: **`retry_number = 0` on every case.** Do not invent retries.

Case **003** is the only FAIL. Retry did **not** fire: the graph only retries when an untried **selectable** model has **strictly better official backtest WIS**. That decision is not written as an event; only `retry_number: 0` remains.

| Required retry story | Official eval |
|---|---|
| Verification passed / WARN and retry not required | PARTIAL (`retry_number: 0`, no “not required” event) |
| Verification failure | PARTIAL (003 `FAIL` string) |
| Failure evidence | MISSING |
| Retry decision (why not / why yes) | MISSING |
| Alternative strategy | MISSING |
| Second execution | Did not occur |
| Second verification | Did not occur |
| Final decision after retry | N/A |

Fixture `verification_retry.jsonl` is a **constructed slice**, not a catalog case.

---

## 9. Human checkpoint coverage

**Where:** After VERIFY, `RETRY_OR_ACCEPT` and `FINALIZE` (`_apply_pending_checkpoint`). Triggers: WARN → `low_forecast_confidence` + `material_uncertainty`; FAIL with no better-WIS retry → `verification_failed_repeatedly`; unused-applied transforms; high analyst/detective uncertainty.

**Real workflow state:** Yes. Graph status becomes `waiting_for_approval`. The graph never auto-approves.

**Official eval:**

- `human_checkpoint_status`: `waiting_for_approval` on all 12
- `review_required`: true on all 12
- `human_intervention_count`: **12**

**This is not 12 human decisions.**

`human_intervention_count` is `sum(1 for row in per_case if row.review_required)` (`evaluation/report.py`). Eval never calls `apply_human_checkpoint`. No Accept / Reject / Review is recorded. The harness still scores holdout and marks the case `status: completed` because a forecast was produced.

API `POST /runs/{id}/checkpoint` **can** persist a `human` `TrajectoryStep` with `action` accept/reject/review. That path is unused by catalog evaluation.

Evaluation mode therefore represents “checkpoint **required**,” not “human **decided**.”

---

## 10. Missing fields (29-item classification)

Classification is against a **real official evaluation run** (`agent-20260830T020331Z`). Fixture-only means the schema/logger can store it, but the official pair does not.

| # | Requirement | Class | Notes |
|---|---|---|---|
| 1 | Run ID | **REAL** | `evaluation_run_id`. Per-case orchestrator `run_id` (`{eval}-{case}`) is not stored |
| 2 | Evaluation case ID | **REAL** | `per_case.case_id` |
| 3 | Dataset metadata | **PARTIAL** | `n_train`, `frequency`, `horizon`, `random_seed`; no CSV name, columns, or profile |
| 4 | Agent identity | **FIXTURE ONLY** | No `agent_id` in official artifacts |
| 5 | Agent input | **FIXTURE ONLY** | Thin `input_summary` in fixtures only |
| 6 | Agent output | **PARTIAL** | Selection + scores; no strategist/analyst reports |
| 7 | Tool invocation | **FIXTURE ONLY** | |
| 8 | Tool arguments | **FIXTURE ONLY** | And those summaries are incomplete |
| 9 | Tool result | **PARTIAL** | Compact backtest + yhat; no tool envelopes |
| 10 | Evidence IDs | **FIXTURE ONLY** | |
| 11 | Decision | **PARTIAL** | `selected_model_id` / `selection_rule` |
| 12 | Model candidates | **PARTIAL** | Executed backtest set; STRATEGY shortlist not stored |
| 13 | Model selection | **REAL** | |
| 14 | Backtest results | **REAL** | Compact official WIS / folds |
| 15 | Robustness / veto | **REAL** | Per-model veto fields |
| 16 | Forecast execution | **PARTIAL** | Arrays present; no FORECAST step / metadata |
| 17 | Verifier invocation | **FIXTURE ONLY** | |
| 18 | Verifier results | **PARTIAL** | Overall only |
| 19 | Retry decision | **PARTIAL** | `retry_number: 0` only |
| 20 | Retry execution | **FIXTURE ONLY** | Catalog had none; fixture is not a case |
| 21 | Human checkpoint | **PARTIAL** | Status / required; no trigger list in JSON |
| 22 | Human decision | **MISSING** | Never applied in eval (API-only) |
| 23 | Final analyst output | **MISSING** | Not in fixtures either |
| 24 | Final result | **PARTIAL** | Holdout + `completed` while still waiting |
| 25 | Errors / failures | **PARTIAL** | Empty `errors[]`; 003 FAIL is not an error row |
| 26 | Timestamps | **PARTIAL** | Run timestamp + `runtime_seconds`; no step clock |
| 27 | Sequence / order | **MISSING** | No event list; case_list order only |
| 28 | Configuration | **REAL** | `selection_policy`, `origin_planning`, pins |
| 29 | Reproducibility metadata | **REAL** | `git_commit`, seeds, library pins |

---

## 11. Security risks

Existing controls (keep):

- Secret key fragments and `sk-` patterns redacted
- Raw series keys (`values`, `timestamps`, …) omitted from summaries
- Artifact ids sanitized; path traversal rejected
- Catalog eval does not send series to a vendor LLM

Risks if persist is later enabled **without** tightening payloads:

- `forecast_fit` evidence currently stores `result.model_dump()` (includes **yhat**)
- Strategist robustness/eval payloads can be large
- `agent.json` already stores full holdout `yhat` (evaluation artifact, not trajectory)

Do not log API keys, headers, or full environment. Do not dump training series into JSONL.

---

## 12. Performance concerns

Official eval persist is **off**, so logging is not on the WIS path today.

Turning persist on with current code would, per case:

- Write ~10–15 orchestrator JSONL lines (one per node; more if retry)
- Write one artifact JSON per tool-bearing step
- Still **not** write child-agent tool sequences unless those persist flags change

That is observational if it only calls `persist_trajectory_step` after existing tools. It must not change selection, WIS, holdout, or models.

Shared `generated_at` is cheap but makes traces look simultaneous.

---

## 13. Recommended minimal implementation

**Do not implement in this audit.** Do not retune forecasting.

Goal: one append-only file per evaluation case that a reviewer can open without reading source.

Keep the existing `TrajectoryRecord` / logger / redaction. Add **additive** fields only:

- `case_id`
- `sequence` (already `step_index` when writing)
- `event_type` (small allowlist below)
- `actor` (already `agent_id`)

Official eval should set `persist_trajectory=True` and write **outside** `evaluation/results/` (e.g. `evaluation/artifacts/trajectories/{evaluation_run_id}/{case_id}.jsonl`) so WIS JSON is unchanged.

Write **child-agent steps to the same file** (same `run_id`, shared `case_id`) instead of `persist_trajectory=False`. That is the smallest way to show detective → strategist tools → robustness → forecast → verify → analyst.

Use `utc_now()` per step (or monotonic `sequence`) so order is visible.

Record explicit **non-events** that reviewers need:

- `RETRY_COMPLETED` is unnecessary if no retry; emit `RETRY_REQUESTED` with `required=false` / reason “WARN or no better official WIS”
- `HUMAN_CHECKPOINT_CREATED` with triggers; `HUMAN_DECISION` only if eval later records a documented catalog policy (or remains `pending`)

Do **not** add extra agents. Do **not** put holdout into the graph. Do **not** persist raw train series. Summarize forecast as `{model, n_yhat, horizon}` and leave numbers in `agent.json`.

Suggested event types (subset of the ask; drop unused):

`RUN_STARTED`, `AGENT_STARTED`, `TOOL_COMPLETED`, `TOOL_FAILED`, `BACKTEST_COMPLETED`, `ROBUSTNESS_ANALYZED`, `MODEL_VETOED`, `MODEL_SELECTED`, `FORECAST_COMPLETED`, `VERIFICATION_COMPLETED`, `RETRY_REQUESTED`, `HUMAN_CHECKPOINT_CREATED`, `HUMAN_DECISION`, `FINAL_ANALYSIS`, `RUN_COMPLETED`, `RUN_FAILED`

`TOOL_STARTED` / `*_STARTED` pairs are optional if `sequence` + one completed event is enough.

---

## 14. Example of the target real trajectory

Illustrative **case 003** (real outcomes: ARIMA selected, VERIFY FAIL, retry 0, waiting). Not an implementation and not a fabricated retry.

```text
Trajectory run_id=agent-20260830T020331Z-003 case_id=003
  1  RUN_STARTED              orchestrator   selection_policy=exp010 origin_planning=model_specific
  2  TOOL_COMPLETED           data_detective inspect_series          eid=E1
  3  TOOL_COMPLETED           data_detective diagnose_seasonality    eid=E6
  4  AGENT_STARTED            forecast_strategist
  5  TOOL_COMPLETED           forecast_strategist evaluate_candidates
  6  ROBUSTNESS_ANALYZED      forecast_strategist R=5
  7  MODEL_SELECTED           forecast_strategist arima official_wis=… rule=official_backtest_wis
  8  FORECAST_COMPLETED       orchestrator  model=arima n_yhat=14
  9  VERIFICATION_COMPLETED   verifier      overall=FAIL  (cite check eids)
 10  RETRY_REQUESTED          orchestrator  required=false reason=no_better_selectable_official_wis
 11  HUMAN_CHECKPOINT_CREATED orchestrator  triggers=[verification_failed_repeatedly] status=waiting
 12  FINAL_ANALYSIS           forecast_analyst  (evidence-cited; no new yhat)
 13  RUN_COMPLETED            orchestrator  graph_status=waiting_for_approval
```

A reviewer should then answer: what was asked → what was observed → which tools ran → what they returned → why ARIMA won → what verify found → why retry did not run → that a human gate is open and **no human clicked**.

---

## Requirement counts (official evaluation)

Against the 29 audit questions (official pair only; fixtures do not count as REAL):

| Class | Count | Items |
|---|---|---|
| **REAL** | **7** | 1 run ID, 2 case ID, 13 selection, 14 backtest, 15 veto, 28 config, 29 repro |
| **PARTIAL** | **12** | 3 metadata, 6 agent output, 9 tool result, 11 decision, 12 candidates, 16 forecast, 18 verifier results, 19 retry decision, 21 checkpoint, 24 final result, 25 errors, 26 timestamps |
| **MISSING** | **3** | 22 human decision, 23 analyst output, 27 event sequence |
| **FIXTURE ONLY** | **7** | 4 agent id, 5 agent input, 7 tool invocation, 8 tool args, 10 evidence IDs, 17 verifier invocation, 20 retry execution |

**12-case trajectory files:** complete **0**, partial **0**, missing **12**.

**12-case outcome rows in `agent.json`:** complete trajectory **0**, partial scorecard **12**, no row **0**.

---

## Stop

No code, evaluation results, WIS, models, selection, threshold, or cases were changed. Next phase (if requested): persist real per-case JSONL only, observational, EXP-010 frozen.
