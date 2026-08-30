# ForecastWize agent evaluation

- evaluation_run_id: `agent-20260829T154616Z`
- timestamp: `2026-08-29T15:46:16.173363Z`
- git_commit: `524837b0ea8a9378f7d9d6601d080eceff602431`
- system: `agent`
- catalog: `forecastwize-eval-v1` v1
- case_list: 001, 002, 003, 004, 005, 006, 007, 008, 009, 010, 011, 012
- wall_seconds: 25.29504459979944

## Aggregate

Official means include **every** registered case. Failed cases are not dropped.
`*_completed_only` is labeled and is **not** the headline result.

- cases completed/failed: 12/0 of 12
- official WIS (headline): 2.43703
- WIS completed-only (not headline): 2.43703
- official sMAPE: 27.0475
- official WMAPE: 21.9177
- official MASE: 2.62077
- official coverage: 0.875397
- official interval width: 18.0148
- human_intervention_count: 12
- cost: —

## Per case

| case_id | status | model | WIS | sMAPE | seconds | error |
|---|---|---|---|---|---|---|
| 001 | completed | arima | 0.0481364 | 0.269934 | 2.790 |  |
| 002 | completed | arima | 0.0905349 | 0.513434 | 2.278 |  |
| 003 | completed | arima | 0.125092 | 0.915362 | 2.615 |  |
| 004 | completed | arima | 2.45547 | 10.2402 | 2.077 |  |
| 005 | completed | arima | 0.163602 | 1.02998 | 2.429 |  |
| 006 | completed | naive | 1.37306 | 1.05659 | 1.625 |  |
| 007 | completed | seasonal_naive | 0.376196 | 1.11956 | 1.775 |  |
| 008 | completed | arima | 0.274475 | 1.00644 | 1.906 |  |
| 009 | completed | arima | 0.377942 | 184.472 | 1.713 |  |
| 010 | completed | seasonal_naive | 0.892381 | 12.9424 | 0.099 |  |
| 011 | completed | arima | 0.23575 | 2.13809 | 3.071 |  |
| 012 | completed | ets | 22.8317 | 108.867 | 2.406 |  |

## Errors

None.

These numbers come from the executable harness, not from hand-edited tables.
Do not treat remembered percentages as the source of truth.
