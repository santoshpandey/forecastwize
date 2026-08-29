# Forecasting methodology

## Implemented

- CSV load (`timestamp`, `value`; optional `series_id`, `context`, `event`, extra columns)
- Validation (required columns, timestamps, numeric values, duplicate timestamps)
- Chronological sort on a **derived** copy; original snapshot is not mutated
- Frequency inference (pandas.infer_freq, min-delta multiples for gaps, median delta)
- Missing-period detection on the inferred regular index
- Conservative deterministic diagnostics: outliers, causal rolling anomalies, trend,
  seasonality, single mean-shift screen (no auto-edit of the series)

- Common `ForecastModel` interface (`fit` / `predict` / `predict_interval` / `metadata`)
  and typed `ForecastResult`
- Shared metrics: MAE, RMSE, sMAPE, WMAPE, MASE, WIS, interval coverage and width
- Explicit baseline models (no LLM, no auto-selection):
  - **Naive:** last observation carried forward; intervals ± z σ √h from first differences
  - **Seasonal naive:** last cycle repeated; period from constructor or frequency
    (D→7, h→24, MS/ME→12, W*→52); variance grows with seasonal repeats
  - **ETS:** additive Holt / Holt–Winters via statsmodels `ExponentialSmoothing`
    (heuristic init, L-BFGS-B); residual √h intervals
  - **ARIMA:** fixed ARIMA(1,1,1), or airline SARIMA(0,1,1)(0,1,1,m) when a seasonal
    period is known — not `auto_arima`
- Explicit frequency, horizon, and rolling-origin backtests (expanding or rolling
  window, configurable `min_train_size` and `step`). Train end is strictly before
  test start. Incomplete tails are not planned. Failed folds stay in the record;
  official aggregate means are None if any fold failed. Ranking by official WIS is
  comparison evidence only — not a generated forecast.
- Shared engine: `run_rolling_origin_backtest`. The `backtest` tool
  (`backend/app/tools/backtest_tools.py`) constructs named baseline models and
  calls that function. Baseline code may call the engine with any `ForecastModel`
  factories.
- Orchestrator (`run_orchestrator`) selects `strategy_id` from official backtest
  WIS over the **full allow-list** (strategy shortlist is a hypothesis), then
  calls `run_baseline_forecast` for generation. Selection and generation stay
  separate. Verification FAIL retries only if an untried model has strictly
  better official backtest WIS.

Training copies are used. Evaluation harnesses apply a named train-only
missing-value policy (`linear_interpolate_train`) after
`split_train_holdout`; holdout and source CSVs are not filled. Fitters still
reject remaining non-finite values. Catalog: `evaluation/cases/` and
`data/evaluation/`. Scores live in generated JSON, not in this page. Cited
official pair: `evaluation/results/comparison.json`
(`comparison-20260829T125254Z`); WIS `relative_improvement` **0.0**.

Every `ForecastResult` includes: `model`, `training_range`, `forecast_horizon`,
`frequency`, `configuration`, `random_seed`, `generated_at` (UTC ISO 8601).

Point accuracy (sMAPE, WMAPE, MASE) and interval scores (WIS, coverage, width)
are computed **separately** in `app.forecasting.metrics`. Both harnesses call
those functions. Backtests use time-aware expanding windows; train timestamps
end before validation. No ordinary-eval row shuffle. Holdout is not passed
into the graph (`holdout_passed_to_graph`: false in
`evaluation/results/agent.json`).

## Planned

- Candidate models beyond the four baselines
- Additional named missing-value and anomaly *repair* policies
- Optional ML only if evaluation evidence shows improvement

