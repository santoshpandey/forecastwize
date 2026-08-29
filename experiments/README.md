# Experiments

ForecastWize records **named experiments** here. An experiment is a hypothesis
plus a change, evaluated with the **same** case catalog and metric functions as
the product harness. Success is not a paragraph. It is an evaluation artifact.

Do not fill **improvement** with remembered percentages. Point at
`evaluation/results/*.json` (`evaluation_run_id` / `comparison_id`).

## Same methodology (required)

From the repository root:

```powershell
python evaluation/run_baseline.py
python evaluation/run_agent.py
python evaluation/compare.py
```

Rules (see `docs/evaluation.md`):

- Identical `case_list` (catalog 001–012) for any baseline vs advanced pair
- Primary metric: official **WIS** over the **full** case list (failures not dropped)
- Secondaries: sMAPE, WMAPE, MASE, interval coverage, interval width, runtime,
  failures, human-intervention count
- `*_completed_only` means are labeled and are **not** the headline

## Required sections

Every `EXP-*.md` file uses these headings:

1. Hypothesis
2. Problem observed
3. Change made
4. Evaluation command
5. Baseline result
6. New result
7. Improvement
8. Failure cases
9. Decision
10. Lesson learned

EXP-006–008 also record the cycle Analyze → Hypothesis → Implement → Test →
Run same benchmark → Compare → Keep / Remove → Document.

Also record **kind**: `baseline` | `iteration` | `removed` | `final`.

Also record **kind**: `baseline` | `iteration` | `removed` | `final`.

If an isolated A/B was **not** run, write **Not measured** under result/improvement
and point at the shared harness. Do not invent scores.

## Index

| ID | Title | Kind | Isolated eval artifact? |
|---|---|---|---|
| [EXP-001](EXP-001-baseline.md) | Conventional baseline harness | baseline | Yes — `evaluation/results/baseline.json` |
| [EXP-002](EXP-002-model-selection.md) | Backtest WIS model selection | iteration | No isolated pair; selection is in both harnesses |
| [EXP-003](EXP-003-anomaly-diagnostics.md) | Anomaly / data diagnostics | iteration | No isolated pair |
| [EXP-004](EXP-004-verification.md) | Forecast verification | iteration | No isolated pair |
| [EXP-005](EXP-005-orchestration.md) | Agent orchestration vs baseline | final | Historical pair; files since overwritten |
| [EXP-INITIAL-COMPARISON](EXP-INITIAL-COMPARISON.md) | First complete catalog benchmark | final | Frozen control — `evaluation/artifacts/exp-initial-comparison/` |
| [EXP-006](EXP-006-missing-policy.md) | Train-only missing-value policy | iteration | Yes — `evaluation/artifacts/EXP-006-missing-policy/` |
| [EXP-007](EXP-007-retry-backtest-wis.md) | Retry only if backtest WIS improves | iteration | Yes — `evaluation/artifacts/EXP-007-retry-backtest-wis/` |
| [EXP-008](EXP-008-full-candidates.md) | Backtest full baseline candidate set | iteration | Yes — `evaluation/artifacts/EXP-008-full-candidates/` (copied to `evaluation/results/`) |

The running summary is [docs/changelog.md](../docs/changelog.md).
