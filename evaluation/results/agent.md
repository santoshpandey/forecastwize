# ForecastWize agent evaluation

- evaluation_run_id: `agent-20260830T030413Z`
- timestamp: `2026-08-30T03:04:13.935369Z`
- git_commit: `524837b0ea8a9378f7d9d6601d080eceff602431`
- system: `agent`
- catalog: `forecastwize-eval-v1` v1
- case_list: 001, 002, 003, 004, 005, 006, 007, 008, 009, 010, 011, 012
- wall_seconds: 45.536693200003356

## Aggregate

Official means include **every** registered case. Failed cases are not dropped.
`*_completed_only` is labeled and is **not** the headline result.

- cases completed/failed: 12/0 of 12
- official WIS (headline): 0.793914
- WIS completed-only (not headline): 0.793914
- official sMAPE: 18.8045
- official WMAPE: 16.8482
- official MASE: 0.76821
- official coverage: 0.928968
- official interval width: 18.0111
- human_intervention_count: 12
- cost: —

## Per case

| case_id | status | model | WIS | sMAPE | seconds | error |
|---|---|---|---|---|---|---|
| 001 | completed | arima | 0.0481364 | 0.269934 | 4.366 |  |
| 002 | completed | arima | 0.0905349 | 0.513434 | 3.277 |  |
| 003 | completed | arima | 0.125092 | 0.915362 | 4.748 |  |
| 004 | completed | arima | 2.45547 | 10.2402 | 5.401 |  |
| 005 | completed | arima | 0.163602 | 1.02998 | 4.590 |  |
| 006 | completed | naive | 1.37306 | 1.05659 | 2.312 |  |
| 007 | completed | seasonal_naive | 0.376196 | 1.11956 | 3.806 |  |
| 008 | completed | arima | 0.274475 | 1.00644 | 3.916 |  |
| 009 | completed | arima | 0.377942 | 184.472 | 2.871 |  |
| 010 | completed | seasonal_naive | 0.892381 | 12.9424 | 1.117 |  |
| 011 | completed | arima | 0.23575 | 2.13809 | 4.667 |  |
| 012 | completed | naive | 3.11433 | 9.95089 | 4.259 |  |

## Errors

None.

These numbers come from the executable harness, not from hand-edited tables.
Do not treat remembered percentages as the source of truth.
