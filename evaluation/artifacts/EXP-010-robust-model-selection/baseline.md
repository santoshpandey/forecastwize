# ForecastWize baseline evaluation

- evaluation_run_id: `baseline-20260830T014058Z`
- timestamp: `2026-08-30T01:40:58.161256Z`
- git_commit: `524837b0ea8a9378f7d9d6601d080eceff602431`
- system: `baseline`
- catalog: `forecastwize-eval-v1` v1
- case_list: 001, 002, 003, 004, 005, 006, 007, 008, 009, 010, 011, 012
- wall_seconds: 20.526084300130606

## Aggregate

Official means include **every** registered case. Failed cases are not dropped.
`*_completed_only` is labeled and is **not** the headline result.

- cases completed/failed: 12/0 of 12
- official WIS (headline): 0.915333
- WIS completed-only (not headline): 0.915333
- official sMAPE: 9.02472
- official WMAPE: 15.199
- official MASE: 1.05935
- official coverage: 0.89881
- official interval width: 21.2854
- human_intervention_count: 0
- cost: —

## Per case

| case_id | status | model | WIS | sMAPE | seconds | error |
|---|---|---|---|---|---|---|
| 001 | completed | naive | 0.454943 | 2.52664 | 1.973 |  |
| 002 | completed | seasonal_naive | 0.132345 | 0.717543 | 1.986 |  |
| 003 | completed | seasonal_naive | 0.435545 | 3.03192 | 2.691 |  |
| 004 | completed | naive | 4.04626 | 13.2471 | 1.461 |  |
| 005 | completed | seasonal_naive | 0.378888 | 2.5176 | 1.480 |  |
| 006 | completed | naive | 1.37306 | 1.05659 | 1.179 |  |
| 007 | completed | naive | 0.308848 | 0.768159 | 1.279 |  |
| 008 | completed | seasonal_naive | 0.338903 | 1.32738 | 1.833 |  |
| 009 | completed | seasonal_naive | 0.418546 | 57.1429 | 1.477 |  |
| 010 | completed | seasonal_naive | 0.892381 | 12.9424 | 0.054 |  |
| 011 | completed | seasonal_naive | 0.826216 | 8.01085 | 2.840 |  |
| 012 | completed | seasonal_naive | 1.37805 | 5.00757 | 2.141 |  |

## Errors

None.

These numbers come from the executable harness, not from hand-edited tables.
Do not treat remembered percentages as the source of truth.
