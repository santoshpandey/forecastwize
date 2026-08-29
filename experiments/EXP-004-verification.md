# EXP-004 Forecast verification

- **Kind:** iteration
- **Status:** implemented; **not** measured as an isolated A/B
- **Date:** 2026-08-29

## Hypothesis

A deterministic verifier that **challenges** a forecast (PASS/WARN/FAIL checks)
will block quiet-accept of a FAIL, allow bounded retries, and escalate to an
explicit human checkpoint when retries are exhausted — without the verifier
emitting or adjusting yhat.

## Problem observed

A graph that only restates metrics is non-compliant. Holdout leakage into
verification during generation would invalidate evaluation. Without a verifier
node, FAIL results could be accepted silently.

## Change made

- `verify_forecast` + `run_verifier` (checks V01–V10)
- Orchestrator VERIFY and RETRY_OR_ACCEPT (max retries = 2)
- FAIL may retry an unused ranked strategy; PASS/WARN proceed to the analyst
- Exhaustion sets `waiting_for_approval` (never auto-approved)

Holdout actuals are **not** passed into the graph in `run_agent.py`. Coverage
and residual checks without holdout are expected to **WARN**, not PASS.

## Evaluation command

Verifier behavior is covered by unit tests. Catalog impact is only visible
inside the full agent run:

```powershell
python evaluation/run_agent.py
python evaluation/compare.py
```

## Baseline result

Not measured in isolation. The baseline harness has no verifier node.

## New result

Not measured as “verifier on vs off.” In `evaluation/results/agent.json` for
`evaluation_run_id` `agent-20260829T090636Z`:

- `aggregate.human_intervention_count` is 0
- Completed cases in that file record `verification_overall` (typically WARN
  when holdout is withheld)
- `retry_number` on completed cases in that run is 0

Do not treat WARN as a measured accuracy win.

## Improvement

**Not computed** for this slice. Official WIS vs baseline is EXP-005 /
`evaluation/results/comparison.json` (headline official WIS is null on both
sides because of case 005).

## Failure cases

- **005** still fails before a trustworthy forecast (non-finite train values).
- No catalog case in this agent run recorded `review_required` / waiting-for-approval
  (`human_intervention_count` 0 in the agent JSON).

## Decision

**Keep** the verifier as a required graph step. Do not skip verification to
improve scores. Do not pass holdout into VERIFY during evaluation.

## Lesson learned

Without holdout, a challenging verifier will often WARN rather than PASS. That
is evidence of uncertainty, not of better WIS. Attribution of retries to
holdout gains needs an experiment that logs retry vs no-retry on the same
cases.
