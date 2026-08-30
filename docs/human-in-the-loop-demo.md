# Human-in-the-loop demonstration

This document describes the **interactive** human checkpoint. It is not a
forecasting experiment and is **not** part of the official 12-case benchmark.

The automated benchmark records checkpoint creation but does not fabricate
human decisions. The interactive demonstration records a HUMAN_DECISION
only when a human actually submits one.

## Purpose

Show that the existing Accept / Reject / Review control is operational: a
real user action writes a `HUMAN_DECISION` event, the run continues, and
the trajectory remains append-only.

Do not use `human_intervention_count` as evidence of a human decision.
Official evaluation counts **checkpoints opened**. Automated catalog runs
open 12 gates and record **0** human decisions.

## Checkpoint lifecycle

```text
HUMAN_CHECKPOINT_CREATED
        ↓
PENDING (status = waiting_for_approval)
        ↓
human action (Accept / Reject / Review)
        ↓
HUMAN_DECISION
        ↓
workflow continuation
        ↓
RUN_COMPLETED   (Accept or Reject only)
```

`HUMAN_CHECKPOINT_CREATED` and `HUMAN_DECISION` are different events.

| Stage | Who | Event | Run status |
|---|---|---|---|
| Gate opens | Graph finalize | `HUMAN_CHECKPOINT_CREATED` | `waiting_for_approval` |
| Graph stops | Graph finalize | `RUN_COMPLETED` with `waiting_for_approval` | still waiting |
| Human acts | UI or `POST /runs/{id}/checkpoint` | `HUMAN_DECISION` | Accept/Reject → `completed`; Review → still waiting |
| Continuation | API after Accept/Reject | second `RUN_COMPLETED` (`continuation_of=HUMAN_DECISION`) | `completed` |

The graph **never** auto-approves. Automated `evaluation/run_agent.py` never
calls `apply_human_checkpoint`.

## What the human sees

The execution, result, and verification screens show
`HumanCheckpointPanel` when a required gate is open:

- Forecast summary and selected model (from the API forecast artifact)
- Verification overall (PASS / WARN / FAIL)
- Risks / warnings and cited evidence IDs
- Proposed transforms (recorded, **not** applied)
- Recommendation: human review is required
- Labeled **Accept**, **Reject**, and **Review**
- Optional note (may be left blank)

The panel does not invent yhat, WIS, or comments.

## Available decisions

| Action | Checkpoint status | Run status | Note |
|---|---|---|---|
| **Accept** | `approved` | `completed` | Recommendation adopted. Source CSV unchanged. |
| **Reject** | `rejected` | `completed` | Recommendation not adopted. Source CSV unchanged. |
| **Review** | still `waiting_for_approval` | still waiting | Gate stays open. A later Accept or Reject is required to finish. |

Blank or whitespace-only notes are stored as no comment. The system does
not invent a reason.

## What gets recorded

On `HUMAN_DECISION` (safe operational fields only):

- `checkpoint_id` (`ckpt-<run_id>`)
- `decision` (`accept` / `reject` / `review`)
- `timestamp` (UTC ISO 8601 on the event)
- `actor` / `agent_id` = `human`
- `checkpoint_status`
- `source_data_unmodified` = true
- associated `evidence_ids`
- `note` **only if** the human actually typed one

Accept/Reject also append `RUN_COMPLETED` with
`continuation_of=HUMAN_DECISION` and the same `checkpoint_id`.

## What is not recorded

- Secrets, API keys, authorization headers
- Internal prompts or private chain-of-thought
- Unnecessary raw series dumps
- Invented comments
- Fabricated retries or agent/tool events
- Holdout values (the interactive graph does not receive official holdout)

## Automated evaluation vs interactive demo

| | Automated 12-case benchmark | Interactive demo |
|---|---|---|
| Location | `evaluation/results/` | `evaluation/artifacts/human-demo/<run-id>/` |
| Selection | Frozen EXP-010 (`selection_policy=exp010`, veto `R=5`) | Same graph defaults; not a scored catalog pair |
| Checkpoints opened | 12 | 1 |
| `HUMAN_DECISION` | **0** (harness never decides) | **1** (human submitted) |
| Official WIS | Baseline `0.9153325914744158`, advanced `0.7939144093884205` | Not a replacement scorecard |

## How to reproduce the demo

1. Copy `.env.example` to `.env`. Leave `OPENAI_API_KEY` empty.
2. Start the API from `backend/`:
   `python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000`
3. Start the UI from `frontend/`: `npm run dev`
4. Upload a supported catalog training series (example: first
   `history_length` rows of `data/evaluation/005_missing_values.csv`).
5. Start a run with the case horizon/frequency/seed (005: horizon **14**,
   frequency **D**, seed **1005**).
6. When the human checkpoint appears, **stop**. Do not script
   `apply_human_checkpoint`.
7. Click **Accept**, **Reject**, or **Review** in the UI (or `POST`
   `/runs/{id}/checkpoint` with the same action after a real choice).
8. Copy the run JSONL from `data/api/trajectories/{run_id}.jsonl` to
   `evaluation/artifacts/human-demo/{run_id}/` with a manifest. Do not
   write into `evaluation/results/`.

Cited demo artifact (real Accept, no invented comment):
`evaluation/artifacts/human-demo/run_f4c8529410f148e8a6f4973abf3440ee/`.

## Safety

The logger redacts secret-like keys and `sk-…` tokens and omits raw
series from summaries. Checkpoint handling refuses to modify the uploaded
CSV. Production API errors stay typed and do not include stack traces.
