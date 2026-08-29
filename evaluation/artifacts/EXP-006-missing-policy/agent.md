# ForecastWize agent evaluation

- evaluation_run_id: `agent-20260829T124543Z`
- timestamp: `2026-08-29T12:45:43.706628Z`
- git_commit: `54c0a145b55808e8f68474f0485c80cb430dbcd3`
- system: `agent`
- catalog: `forecastwize-eval-v1` v1
- case_list: 001, 002, 003, 004, 005, 006, 007, 008, 009, 010, 011, 012
- wall_seconds: 11.970495499903336

## Aggregate

Official means include **every** registered case. Failed cases are not dropped.
`*_completed_only` is labeled and is **not** the headline result.

- cases completed/failed: 12/0 of 12
- official WIS (headline): 1.1343
- WIS completed-only (not headline): 1.1343
- official sMAPE: 8.12879
- official WMAPE: 13.9554
- official MASE: 1.7704
- official coverage: 0.952381
- official interval width: 26.7634
- human_intervention_count: 12
- cost: —

## Per case

| case_id | status | model | WIS | sMAPE | seconds | error |
|---|---|---|---|---|---|---|
| 001 | completed | naive | 0.454943 | 2.52664 | 1.667 |  |
| 002 | completed | seasonal_naive | 0.132345 | 0.717543 | 0.251 |  |
| 003 | completed | naive | 2.67648 | 19.8407 | 2.020 |  |
| 004 | completed | naive | 4.04626 | 13.2471 | 0.212 |  |
| 005 | completed | seasonal_naive | 0.378888 | 2.5176 | 0.249 |  |
| 006 | completed | naive | 1.37306 | 1.05659 | 1.137 |  |
| 007 | completed | naive | 0.308848 | 0.768159 | 1.268 |  |
| 008 | completed | seasonal_naive | 0.338903 | 1.32738 | 0.226 |  |
| 009 | completed | naive | 0.649078 | 28.5714 | 0.160 |  |
| 010 | completed | naive | 1.04856 | 13.9539 | 0.079 |  |
| 011 | completed | seasonal_naive | 0.826216 | 8.01085 | 2.692 |  |
| 012 | completed | seasonal_naive | 1.37805 | 5.00757 | 1.901 |  |

## Errors

None.

These numbers come from the executable harness, not from hand-edited tables.
Do not treat remembered percentages as the source of truth.
