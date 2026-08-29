# ForecastWize agent evaluation

- evaluation_run_id: `agent-20260829T125021Z`
- timestamp: `2026-08-29T12:50:21.234368Z`
- git_commit: `54c0a145b55808e8f68474f0485c80cb430dbcd3`
- system: `agent`
- catalog: `forecastwize-eval-v1` v1
- case_list: 001, 002, 003, 004, 005, 006, 007, 008, 009, 010, 011, 012
- wall_seconds: 12.050874100066721

## Aggregate

Official means include **every** registered case. Failed cases are not dropped.
`*_completed_only` is labeled and is **not** the headline result.

- cases completed/failed: 12/0 of 12
- official WIS (headline): 0.947559
- WIS completed-only (not headline): 0.947559
- official sMAPE: 6.72806
- official WMAPE: 12.635
- official MASE: 1.07402
- official coverage: 0.922619
- official interval width: 23.7824
- human_intervention_count: 12
- cost: —

## Per case

| case_id | status | model | WIS | sMAPE | seconds | error |
|---|---|---|---|---|---|---|
| 001 | completed | naive | 0.454943 | 2.52664 | 1.663 |  |
| 002 | completed | seasonal_naive | 0.132345 | 0.717543 | 0.266 |  |
| 003 | completed | seasonal_naive | 0.435545 | 3.03192 | 2.018 |  |
| 004 | completed | naive | 4.04626 | 13.2471 | 0.167 |  |
| 005 | completed | seasonal_naive | 0.378888 | 2.5176 | 0.262 |  |
| 006 | completed | naive | 1.37306 | 1.05659 | 1.163 |  |
| 007 | completed | naive | 0.308848 | 0.768159 | 1.304 |  |
| 008 | completed | seasonal_naive | 0.338903 | 1.32738 | 0.235 |  |
| 009 | completed | naive | 0.649078 | 28.5714 | 0.156 |  |
| 010 | completed | naive | 1.04856 | 13.9539 | 0.105 |  |
| 011 | completed | seasonal_naive | 0.826216 | 8.01085 | 2.634 |  |
| 012 | completed | seasonal_naive | 1.37805 | 5.00757 | 1.966 |  |

## Errors

None.

These numbers come from the executable harness, not from hand-edited tables.
Do not treat remembered percentages as the source of truth.
