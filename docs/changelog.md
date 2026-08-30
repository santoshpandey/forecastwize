# Changelog

This file summarizes **experiments**, not every code drop. Implementation
detail lives in [architecture.md](architecture.md) and
[agent-design.md](agent-design.md). Scores live in evaluation JSON, not here.

## Hackathon summary (cited artifacts only)

| Item | Statement | Artifact |
|---|---|---|
| Official WIS vs baseline | `relative_improvement` **0.13264925035654543** (~13.26%) | `evaluation/results/comparison.json` (`comparison-20260830T030644Z`) |
| **Biggest improvement** | Official catalog WIS **13.26%**; largest per-case holdout gain **001** (ARIMA) | official `comparison.json`; EXP-010 isolate `comparison-20260830T014245Z` |
| **Biggest failure** | Case **012** still loses holdout WIS (naive 3.114 vs baseline SN 1.378); 12 checkpoints opened, 0 human decisions | same official `comparison.json` case 012 |
| **Removed experiment** | EXP-009 model-specific origins without veto (WIS −1.662); catastrophic 012 ETS | `evaluation/artifacts/EXP-009-ets-arima-min-train/` |
| **Main engineering lesson** | Official mean WIS can hide a collapsing last fold; gate unstable candidates, do not blend or hard-code a model | EXP-009 failed; EXP-010 promoted |

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

## Human-in-the-loop demo (not a WIS experiment)

- **Kind:** iteration (interactive checkpoint only)
- **Record:** [docs/human-in-the-loop-demo.md](human-in-the-loop-demo.md)
- **Artifact:** `evaluation/artifacts/human-demo/run_f4c8529410f148e8a6f4973abf3440ee/`
  (not `evaluation/results/`)
- One real interactive run records `HUMAN_CHECKPOINT_CREATED` and, after a
  human Accept / Reject / Review, one `HUMAN_DECISION`. Official catalog
  remains **12 checkpoints opened, 0 human decisions**. EXP-010 and official
  WIS are unchanged.

---

## Trajectory observability (not a WIS experiment)

- **Kind:** iteration (observability only)
- **Record:** [docs/trajectory-evidence.md](trajectory-evidence.md),
  [experiments/EXP-TRAJECTORY-AUDIT.md](../experiments/EXP-TRAJECTORY-AUDIT.md)
- **Command:** `python evaluation/run_agent.py`
- **Artifact:** `evaluation/results/trajectories/agent-20260830T030413Z/`
- Official catalog persist is now on by default. Child agents append to the
  same per-case JSONL. WIS, selected models, verification, and retries were
  unchanged vs the pre-persist EXP-010 pair
  (`comparison-20260830T020453Z` → `comparison-20260830T030644Z`, same
  headline WIS **0.13264925035654543**).
- Evaluation `human_intervention_count` remains **12 open checkpoints**, not
  12 human decisions. No `HUMAN_DECISION` events were fabricated.

---

## Baseline

### EXP-001 Conventional baseline harness

- **Kind:** baseline
- **Record:** [experiments/EXP-001-baseline.md](../experiments/EXP-001-baseline.md)
- **Command:** `python evaluation/run_baseline.py`
- **Artifact:** `evaluation/results/baseline.json`
- **evaluation_run_id:** `baseline-20260829T071344Z` (later overwritten).
  The EXP-008 official copy (`baseline-20260829T125209Z`) is archived at
  `evaluation/artifacts/pre-exp010-promotion/`. Current official
  `evaluation/results/baseline.json` is `baseline-20260830T020244Z`
  (EXP-010 promotion). Frozen first catalog pair:
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
  (`comparison-20260829T125254Z`); then copied to `evaluation/results/`
  (those official files were later overwritten by EXP-010)
- **What changed:** BACKTEST executes the allow-list (`BASELINE_MODEL_IDS`);
  strategy shortlist remains a hypothesis.

**Decision:** **Keep.** Official WIS **parity** with baseline
(`relative_improvement` **0.0**). Not a win. Cases 009/010 matched baseline
`seasonal_naive`.

### EXP-010 Robust model selection (planner + last/earlier veto)

- **Kind:** iteration
- **Record:** [experiments/EXP-010-robust-model-selection.md](../experiments/EXP-010-robust-model-selection.md)
- **Isolated eval:** `evaluation/artifacts/EXP-010-robust-model-selection/`
  (`baseline-20260830T014058Z` / `agent-20260830T014147Z` /
  `comparison-20260830T014245Z`)
- **What changed:** `--selection-policy exp010` uses model-specific origins
  plus a frozen last/earlier fold-WIS veto (`R=5`). Ranking stays official
  backtest WIS among models that pass. After the isolated run succeeded,
  this became the official advanced default.

**Headline:** official WIS baseline **0.9153325914744158** vs agent
**0.7939144093884205**, `relative_improvement` **0.13264925035654543**.
All 12 cases; `n_cases_failed` 0. Agent won **8**, lost **2**, tied **2**.
Case **012** selected naive (ETS / seasonal_naive / ARIMA vetoed); holdout
WIS 3.114 vs EXP-009 ETS 22.83 — still worse than baseline SN 1.378.

**Decision:** **Promote** to the official advanced solution. See
[EXP-010-PROMOTION.md](../experiments/EXP-010-PROMOTION.md). Do not retune
`R`. Do not start EXP-011.

---

## Removed experiment

### EXP-009 Model-specific ETS/ARIMA backtest origins (removed from default path)

- **Kind:** removed experiment
- **Record:** [experiments/EXP-009-ets-arima-min-train.md](../experiments/EXP-009-ets-arima-min-train.md)
- **Isolated eval:** `evaluation/artifacts/EXP-009-ets-arima-min-train/`
  (`baseline-20260829T154533Z` / `agent-20260829T154616Z` /
  `comparison-20260829T154706Z`)
- **What changed:** Agent `evaluate_candidates` planned expanding origins per
  model using `ForecastModel.minimum_train_size`. Baseline still uses shared
  `run_rolling_origin_backtest`. Selection remained official backtest WIS.

**Headline:** official WIS baseline **0.91533** vs agent **2.43703**,
`relative_improvement` **−1.662**. All 12 cases evaluated; `n_cases_failed` 0.
Agent won **8** cases, lost **2**, tied **2**. Case **012** ETS holdout WIS
**22.83** vs **1.38** dominates the mean.

**Decision:** **Remove from the default advanced path.** Do not describe
EXP-009 as successful. Code remains as an explicit historical opt-in
(`python evaluation/run_agent.py --origin-planning model_specific`, or
`--origin-planning model_specific --selection-policy default`) so the
isolated pair can be reproduced. Official advanced is EXP-010, not EXP-009.
Do not treat per-case ARIMA wins as a catalog success.

---

## Final solution

### Current official pair (promoted EXP-010)

- **Kind:** final solution
- **Record:** [experiments/EXP-010-robust-model-selection.md](../experiments/EXP-010-robust-model-selection.md),
  [EXP-010-PROMOTION.md](../experiments/EXP-010-PROMOTION.md)
- **Commands** (no experimental flag required):

```powershell
python evaluation/run_baseline.py
python evaluation/run_agent.py
python evaluation/compare.py
```

- **Artifacts (current `evaluation/results/`):**
  - `baseline.json` (`baseline-20260830T020244Z`)
  - `agent.json` (`agent-20260830T030413Z`; same WIS as `agent-20260830T020331Z`)
  - `comparison.json` (`comparison-20260830T030644Z`)
  - trajectories: `evaluation/results/trajectories/agent-20260830T030413Z/`
- **case_list:** 001–012, identical (`case_lists_identical` true)
- Previous official EXP-008 pair archived at
  `evaluation/artifacts/pre-exp010-promotion/`

Official aggregate WIS: baseline **0.9153325914744158**, advanced
**0.7939144093884205**, `relative_improvement` **0.13264925035654543**
(~13.26%). Holdout outcomes: **8** advanced wins, **2** baseline wins,
**2** ties. `n_cases_failed` is 0. Automated evaluation opened **12**
checkpoints and recorded **0** human decisions (`human_intervention_count`
counts checkpoints opened).

**Evolution (do not rewrite):** EXP-008 produced shared-origin **parity**.
EXP-009 allowed stronger models to compete and **failed** on case 012
(ETS holdout WIS ~22.83). EXP-010 kept the planner, added the instability
veto, and became official after the measured WIS win.

**Decision:** keep EXP-006+007+008+010. Official advanced is EXP-010.
**Do not** start EXP-011 or retune `R`.

### Previous official pair (EXP-008; superseded files)

- **Kind:** final solution (superseded **files**; record kept)
- **Record:** [experiments/EXP-008-full-candidates.md](../experiments/EXP-008-full-candidates.md)
- **Archived files:** `evaluation/artifacts/pre-exp010-promotion/` and
  `evaluation/artifacts/EXP-008-full-candidates/`
  (`baseline-20260829T125209Z` / `agent-20260829T125231Z` /
  `comparison-20260829T125254Z`)
- Official aggregate WIS `relative_improvement` was **0.0** (parity).

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

Verifier **WARN** still opens a human checkpoint on every completed
evaluation case (`human_intervention_count` 12 = checkpoints opened, not
human decisions). That is not an official WIS failure. Case **012** still loses holdout WIS after EXP-010. Case
**005** completes under the named train-only missing policy (EXP-006); it
no longer nulls official WIS.

**Main engineering lesson:** execute the same candidate set and metric code
as the baseline; retry only on strictly better official backtest WIS; fill
missing train values only with a named, logged policy.
