# Changelog

This file summarizes **experiments**, not every code drop. Implementation
detail lives in [architecture.md](architecture.md) and
[agent-design.md](agent-design.md). Scores live in evaluation JSON, not here.

## Hackathon summary (cited artifacts only)

| Item | Statement | Artifact |
|---|---|---|
| Official WIS vs baseline | `relative_improvement` **0.0** (parity, not a win) | `evaluation/results/comparison.json` (`comparison-20260829T125254Z`) |
| **Biggest improvement** | Case **003** WIS relative **-5.145…** → **0.0** after retry-only-if-better-WIS; EXP-006 made official WIS non-null | EXP-006 `comparison-20260829T124600Z`; EXP-007 `comparison-20260829T125037Z` |
| **Biggest failure** | No official WIS win; agent `human_intervention_count` **12** vs baseline **0** | same official `comparison.json` `aggregate.human_intervention_count` |
| **Removed experiment** | **None** | this file, section below |
| **Main engineering lesson** | Do not execute a hypothesis shortlist or retry to a worse official backtest WIS; use a named train-only missing policy | EXP-006–008 records |

**Kinds** used below:

| Kind | Meaning |
|---|---|
| **baseline** | Conventional system; defines the reference run |
| **iteration** | A change toward the advanced path; isolated WIS may be unmeasured |
| **removed experiment** | Tried, then dropped (why, with artifacts if any) |
| **final solution** | Current advanced evaluation path vs the baseline |

Same methodology whenever possible: `python evaluation/run_baseline.py`,
`python evaluation/run_agent.py`, `python evaluation/compare.py`. Catalog
001–012. Official WIS includes failed cases. Named records:
[experiments/README.md](../experiments/README.md).

---

## Baseline

### EXP-001 Conventional baseline harness

- **Kind:** baseline
- **Record:** [experiments/EXP-001-baseline.md](../experiments/EXP-001-baseline.md)
- **Command:** `python evaluation/run_baseline.py`
- **Artifact:** `evaluation/results/baseline.json`
- **evaluation_run_id:** `baseline-20260829T071344Z` (later overwritten).
  Current `evaluation/results/baseline.json` is `baseline-20260829T125209Z`
  (EXP-008 copy). Frozen first catalog pair:
  `evaluation/artifacts/exp-initial-comparison/`.

The first complete catalog run had **null** official WIS (case **005**
failed). After EXP-006 the official mean is non-null. Failed cases are never
dropped. Completed-only means are **not** the headline.

**Decision:** keep this harness as the conventional reference.

---

## Iteration

EXP-002–004 and checkpoints were **not** scored as standalone catalog A/B
runs. EXP-006–008 each have an isolated artifact pair. Do not treat any
iteration as an official WIS **win** unless `relative_improvement` is
positive in that comparison JSON.

### EXP-002 Model selection from official backtest WIS

- **Kind:** iteration
- **Record:** [experiments/EXP-002-model-selection.md](../experiments/EXP-002-model-selection.md)
- **Isolated eval:** none
- **What changed:** `strategy_id` only from executed backtest WIS (shared engine
  with the baseline harness). No LLM picking.

**Decision:** keep `official_backtest_wis` as the only superiority rule.

### EXP-003 Anomaly and data diagnostics

- **Kind:** iteration
- **Record:** [experiments/EXP-003-anomaly-diagnostics.md](../experiments/EXP-003-anomaly-diagnostics.md)
- **Isolated eval:** none
- **What changed:** explicit detect-and-record diagnostics; series not mutated;
  no yhat from the detective.

**Decision:** keep diagnostics. Do not add silent imputation to chase WIS.

### EXP-004 Forecast verification

- **Kind:** iteration
- **Record:** [experiments/EXP-004-verification.md](../experiments/EXP-004-verification.md)
- **Isolated eval:** none
- **What changed:** deterministic PASS/WARN/FAIL verifier; FAIL is not
  quiet-accepted; bounded retries; exhaustion waits for human approval.

**Decision:** keep verification required before accept. Do not pass holdout
into the graph during evaluation.

### Human-in-the-loop checkpoints

- **Kind:** iteration
- **Isolated eval:** none
- **What changed:** Accept / Reject / Review via `POST /runs/{id}/checkpoint`.
  Gates fire on proposed data modification, low confidence, repeated
  verification failure, and remaining material uncertainty. Rejections are
  appended to the run trajectory. Source data is never modified. The graph
  does not auto-approve.

**Decision:** keep the explicit human gate. Do not treat UI navigation as
approval.

### Security hardening (uploads, Docker bind, job cap)

- **Kind:** iteration
- **Isolated eval:** none
- **What changed:** Upload `Content-Length` required and size-capped; store
  paths refuse escape from the API directory; changelog read confined to
  `docs/changelog.md`; production hides OpenAPI; Compose publishes localhost
  only and runs containers as non-root; inflight background jobs capped;
  log exception text redacts `sk-` / secret-like substrings. No WIS claim.

**Decision:** keep these controls. Authentication remains Planned.

### EXP-006 Train-only missing-value policy

- **Kind:** iteration
- **Record:** [experiments/EXP-006-missing-policy.md](../experiments/EXP-006-missing-policy.md)
- **Isolated eval:** `evaluation/artifacts/EXP-006-missing-policy/`
  (`comparison-20260829T124600Z`)
- **What changed:** named `linear_interpolate_train` on the **training** copy
  after split, both harnesses. Source CSVs and holdout are not filled.

**Decision:** **Keep.** Official WIS became non-null. Agent was still worse
than baseline on that pair (`wis.relative_improvement` −0.2392).

### EXP-007 Retry only if official backtest WIS improves

- **Kind:** iteration
- **Record:** [experiments/EXP-007-retry-backtest-wis.md](../experiments/EXP-007-retry-backtest-wis.md)
- **Isolated eval:** `evaluation/artifacts/EXP-007-retry-backtest-wis/`
  (`comparison-20260829T125037Z`)
- **What changed:** verification FAIL retries only when the next untried
  model has strictly lower official backtest WIS.

**Decision:** **Keep.** Case 003 matched baseline WIS. Agent official WIS
improved vs EXP-006; vs baseline `relative_improvement` was still negative
(−0.0352).

### EXP-008 Backtest the full baseline candidate set

- **Kind:** iteration
- **Record:** [experiments/EXP-008-full-candidates.md](../experiments/EXP-008-full-candidates.md)
- **Isolated eval:** `evaluation/artifacts/EXP-008-full-candidates/`
  (`comparison-20260829T125254Z`); copied to `evaluation/results/`
- **What changed:** BACKTEST executes the allow-list (`BASELINE_MODEL_IDS`);
  strategy shortlist remains a hypothesis.

**Decision:** **Keep.** Official WIS **parity** with baseline
(`relative_improvement` **0.0**). Not a win. Cases 009/010 matched baseline
`seasonal_naive`.

---

## Removed experiment

**None.** No approach was evaluated and then withdrawn. This section stays
so later removals are not deleted from history.

---

## Final solution

### Current official pair (EXP-008 copy)

- **Kind:** final solution
- **Record:** [experiments/EXP-008-full-candidates.md](../experiments/EXP-008-full-candidates.md)
- **Commands:**

```powershell
python evaluation/run_baseline.py
python evaluation/run_agent.py
python evaluation/compare.py
```

- **Artifacts (current `evaluation/results/`):**
  - `baseline.json` (`baseline-20260829T125209Z`)
  - `agent.json` (`agent-20260829T125231Z`)
  - `comparison.json` (`comparison-20260829T125254Z`)
- **case_list:** 001–012, identical (`case_lists_identical` true)

Official aggregate WIS `relative_improvement` is **0.0** (parity). Advanced
did **not** beat baseline on WIS for any case. `n_cases_failed` is 0.
Human interventions: **12** (agent, every case WARNs) vs **0** (baseline).
Do not report this as a WIS win.

**Decision:** keep EXP-006+007+008. **Do not** claim an official WIS
improvement.

### EXP-INITIAL-COMPARISON First complete catalog benchmark

- **Kind:** final solution (superseded **files**; record kept)
- **Record:** [experiments/EXP-INITIAL-COMPARISON.md](../experiments/EXP-INITIAL-COMPARISON.md)
- **Frozen files:** `evaluation/artifacts/exp-initial-comparison/`
  (`baseline-20260829T123106Z` / `agent-20260829T123136Z` /
  `comparison-20260829T123158Z`)
- Official WIS **null** (005 failed both sides). Agent WIS losses on 003,
  009, 010. Human interventions: 11.

### EXP-005 Agent orchestration vs baseline (earlier pair)

- **Kind:** final solution (superseded **files**; record kept)
- **Record:** [experiments/EXP-005-orchestration.md](../experiments/EXP-005-orchestration.md)
- **Note:** That write-up cited `baseline-20260829T071344Z` /
  `agent-20260829T090636Z` / `comparison-20260829T090720Z`.

---

## Standing limitation (not a removed experiment)

Verifier **WARN** still requires a human checkpoint on every completed
evaluation case (`human_intervention_count` 12). That is not an official
WIS failure. Case **005** completes under the named train-only missing
policy (EXP-006); it no longer nulls official WIS.

**Main engineering lesson:** execute the same candidate set and metric code
as the baseline; retry only on strictly better official backtest WIS; fill
missing train values only with a named, logged policy.
