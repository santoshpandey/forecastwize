# ForecastWize agent evaluation

- evaluation_run_id: `agent-20260830T014147Z`
- timestamp: `2026-08-30T01:41:47.250800Z`
- git_commit: `524837b0ea8a9378f7d9d6601d080eceff602431`
- system: `agent`
- catalog: `forecastwize-eval-v1` v1
- case_list: 001, 002, 003, 004, 005, 006, 007, 008, 009, 010, 011, 012
- wall_seconds: 28.431482800049707

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
| 001 | completed | arima | 0.0481364 | 0.269934 | 3.247 |  |
| 002 | completed | arima | 0.0905349 | 0.513434 | 2.524 |  |
| 003 | completed | arima | 0.125092 | 0.915362 | 2.950 |  |
| 004 | completed | arima | 2.45547 | 10.2402 | 2.273 |  |
| 005 | completed | arima | 0.163602 | 1.02998 | 2.550 |  |
| 006 | completed | naive | 1.37306 | 1.05659 | 1.622 |  |
| 007 | completed | seasonal_naive | 0.376196 | 1.11956 | 2.450 |  |
| 008 | completed | arima | 0.274475 | 1.00644 | 2.405 |  |
| 009 | completed | arima | 0.377942 | 184.472 | 1.898 |  |
| 010 | completed | seasonal_naive | 0.892381 | 12.9424 | 0.111 |  |
| 011 | completed | arima | 0.23575 | 2.13809 | 3.507 |  |
| 012 | completed | naive | 3.11433 | 9.95089 | 2.761 |  |

## Errors

None.

These numbers come from the executable harness, not from hand-edited tables.
Do not treat remembered percentages as the source of truth.
