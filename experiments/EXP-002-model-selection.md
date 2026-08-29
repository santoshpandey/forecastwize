# EXP-002 Model selection from official backtest WIS

- **Kind:** iteration
- **Status:** implemented; **not** measured as an isolated A/B
- **Date:** 2026-08-29

## Hypothesis

Selecting `strategy_id` only from **executed** rolling-origin backtest WIS
(never from an LLM preference) produces a defensible model choice on the shared
catalog, and is a prerequisite for any later claim that the agentic path is
better than a fixed `model_id`.

## Problem observed

A hardcoded or LLM-picked model would not be comparable to the baseline
harness, which already ranks candidates on train-only backtests. Selection and
generation must stay separate.

## Change made

- Shared engine: `run_rolling_origin_backtest`
- Agent: `run_forecast_strategist` + `evaluate_candidates` (compact official WIS
  snapshots, no production yhat)
- Superiority is allowed only when `selection_rule` is `official_backtest_wis`
  and backtesting actually ran

The baseline harness uses the same ranking idea (`run_baseline.py`). The agent
graph uses the strategist, then `run_baseline_forecast` for generation.

## Evaluation command

Same catalog and metrics as EXP-001. There was **no** extra script that scores
“strategist on vs off” alone.

To reproduce the **full** agent path (which includes this selection):

```powershell
python evaluation/run_agent.py
python evaluation/compare.py
```

## Baseline result

Not measured in isolation. The conventional baseline already selects by
backtest WIS; see EXP-001 / `evaluation/results/baseline.json`.

## New result

Not measured in isolation. Unit tests cover strategist failure modes (missing
diagnostics, unsupported models, no superiority without a backtest). They are
not holdout WIS.

## Improvement

**Not computed.** No paired `evaluation_run_id` exists for this change by
itself. Do not infer a WIS delta from unit tests.

## Failure cases

Not separately tabulated for this iteration. Catalog case **005** still fails
on non-finite train values in both full harnesses (see EXP-001 and EXP-005).

## Decision

**Keep** official backtest WIS as the only rule that may recommend a
`strategy_id`. Do not add LLM model picking. Do not treat this iteration as a
measured win.

## Lesson learned

If baseline and agent both select from the same backtest evidence, any later
WIS difference must come from **other** graph behavior (retries, candidate
shortlist, verification), not from “we invented backtesting.” Isolated
selection A/Bs need their own artifact if we want to attribute that slice.
