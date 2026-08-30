# Human-in-the-loop demo

This folder is **not** an official evaluation result. It is one interactive
run of the existing API after a real human Accept.

The automated benchmark records checkpoint creation but does not fabricate
human decisions. The interactive demonstration records a HUMAN_DECISION
only when a human actually submits one.

| Field | Value |
|---|---|
| `run_id` | `run_f4c8529410f148e8a6f4973abf3440ee` |
| Dataset | Catalog case **001** train window (180 daily rows from `data/evaluation/001_trend.csv`) |
| Horizon / frequency / seed | 14 / `D` / 1001 |
| Selection | Frozen EXP-010 (`exp010`, model-specific origins, `R=5`) |
| Selected model | `arima` |
| Verification | WARN |
| Checkpoint | `ckpt-run_f4c8529410f148e8a6f4973abf3440ee` created, then **Accept** |
| Human note | none (not invented) |
| Final status | `completed`, `accepted=true` |
| Trajectory | `trajectory.jsonl` (52 events) |
| Tool artifacts | `artifacts/` |

Official 12-case pair remains `evaluation/results/comparison.json`
(`comparison-20260830T030644Z`): baseline WIS `0.9153325914744158`,
advanced WIS `0.7939144093884205`. Official catalog trajectories still
have 12 `HUMAN_CHECKPOINT_CREATED` and 0 `HUMAN_DECISION`.
