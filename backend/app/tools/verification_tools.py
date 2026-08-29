"""Deterministic forecast verification checks. Challenges artifacts; does not emit yhat.

Does not fit models, does not modify caller arrays, and does not override its own
results. No FastAPI. No LLM.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

import numpy as np
import pandas as pd
from pydantic import BaseModel, ConfigDict, Field

from app.data.seasonality import diagnose_seasonality, diagnose_trend, period_from_frequency
from app.data.structural_breaks import diagnose_structural_breaks
from app.forecasting.base import ForecastInterfaceError, ForecastResult
from app.forecasting.intervals import IntervalOrderError
from app.forecasting.metrics import interval_coverage, interval_width

VERIFY_FORECAST = "verify_forecast"
VERIFICATION_TOOL_NAMES = (VERIFY_FORECAST,)

CheckResult = Literal["PASS", "WARN", "FAIL"]
Severity = Literal["low", "medium", "high"]
JsonObject = dict[str, Any]

CHECK_FORECAST_BOUNDS = "V01_forecast_bounds"
CHECK_HISTORICAL_RANGE = "V02_historical_range"
CHECK_TREND_CONSISTENCY = "V03_trend_consistency"
CHECK_SEASONALITY_CONSISTENCY = "V04_seasonality_consistency"
CHECK_RESIDUAL_DIAGNOSTICS = "V05_residual_diagnostics"
CHECK_INTERVAL_COVERAGE = "V06_interval_coverage"
CHECK_INTERVAL_WIDTH = "V07_interval_width"
CHECK_REGIME_CHANGE = "V08_regime_change_risk"
CHECK_EXTREME_GROWTH = "V09_extreme_growth"
CHECK_INVALID_VALUES = "V10_invalid_values"

# Documented thresholds. Not evaluation scores.
_RANGE_FAIL_IQR = 8.0
_GROWTH_WARN = 3.0
_GROWTH_FAIL = 5.0
_COVERAGE_WARN_GAP = 0.10
_COVERAGE_FAIL_GAP = 0.25
_WIDTH_TIGHT_FRAC = 0.01
_WIDTH_WARN_MULT = 20.0
_WIDTH_FAIL_MULT = 50.0
_BIAS_WARN_Z = 2.0
_BIAS_FAIL_Z = 3.0
_ACF_WARN = 0.5
_TREND_SLOPE_FRAC = 0.1
_SEASON_FAIL_CORR = -0.3
_SEASON_WARN_CORR = 0.2


class ForecastSnapshot(BaseModel):
    """Forecast arrays for verification. Invalid values are allowed so checks can FAIL."""

    model_config = ConfigDict(extra="forbid")

    yhat: list[float]
    lower: list[float]
    upper: list[float]
    forecast_horizon: int
    frequency: str
    timestamps: list[datetime] | None = None
    model: str | None = None
    interval_coverage_nominal: float | None = 0.95


class VerifyForecastSpec(BaseModel):
    """Allowlisted verification arguments. Unknown fields are rejected."""

    model_config = ConfigDict(extra="forbid")

    seasonal_period: int | None = None
    nominal_coverage: float | None = None


class VerificationCheck(BaseModel):
    """One deterministic challenge. Interpretation must not silently rewrite `result`."""

    model_config = ConfigDict(extra="forbid")

    check_id: str
    name: str
    result: CheckResult
    severity: Severity
    explanation: str
    evidence: JsonObject
    applicable: bool = True


class VerifyForecastResult(BaseModel):
    """Full deterministic verification payload. No production yhat."""

    model_config = ConfigDict(extra="forbid")

    overall_result: CheckResult
    n_fail: int
    n_warn: int
    n_pass: int
    checks: list[VerificationCheck]
    limitations: list[str] = Field(default_factory=list)
    challenged: bool
    summary: str


class VerificationToolEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tool_name: str
    ok: bool
    payload: JsonObject
    error_type: str | None = None
    error_message: str | None = None


def snapshot_from_forecast_result(result: ForecastResult) -> ForecastSnapshot:
    return ForecastSnapshot(
        yhat=list(result.yhat),
        lower=list(result.lower),
        upper=list(result.upper),
        forecast_horizon=result.forecast_horizon,
        frequency=result.frequency,
        timestamps=list(result.timestamps),
        model=result.model,
        interval_coverage_nominal=result.interval_coverage_nominal,
    )


def reject_unknown_verification_tool(name: str) -> None:
    if name not in VERIFICATION_TOOL_NAMES:
        allowed = ", ".join(VERIFICATION_TOOL_NAMES)
        msg = f"Unknown tool {name!r}. Approved verification tools: {allowed}."
        raise ForecastInterfaceError(msg)


def run_named_verification_tool(
    name: str,
    *,
    train_values: pd.Series | np.ndarray | list[float] | None = None,
    forecast: ForecastSnapshot | ForecastResult | None = None,
    train_timestamps: pd.Series | pd.DatetimeIndex | None = None,
    actuals: pd.Series | np.ndarray | list[float] | None = None,
    residuals: pd.Series | np.ndarray | list[float] | None = None,
    spec: VerifyForecastSpec | None = None,
) -> VerificationToolEnvelope:
    reject_unknown_verification_tool(name)
    return run_verify_forecast_tool(
        train_values=train_values,
        forecast=forecast,
        train_timestamps=train_timestamps,
        actuals=actuals,
        residuals=residuals,
        spec=spec,
    )


def run_verify_forecast_tool(
    *,
    train_values: pd.Series | np.ndarray | list[float] | None,
    forecast: ForecastSnapshot | ForecastResult | None,
    train_timestamps: pd.Series | pd.DatetimeIndex | None = None,
    actuals: pd.Series | np.ndarray | list[float] | None = None,
    residuals: pd.Series | np.ndarray | list[float] | None = None,
    spec: VerifyForecastSpec | None = None,
) -> VerificationToolEnvelope:
    """Run all verification checks on copies of the inputs. Does not fit a model."""
    if forecast is None:
        msg = "verify_forecast requires a forecast snapshot"
        return VerificationToolEnvelope(
            tool_name=VERIFY_FORECAST,
            ok=False,
            payload={"summary": msg},
            error_type="MissingForecast",
            error_message=msg,
        )
    if train_values is None:
        msg = "verify_forecast requires a training series"
        return VerificationToolEnvelope(
            tool_name=VERIFY_FORECAST,
            ok=False,
            payload={"summary": msg},
            error_type="MissingTrainingSeries",
            error_message=msg,
        )
    train = _copy_float(train_values)
    if train.size == 0:
        msg = "training series is empty"
        return VerificationToolEnvelope(
            tool_name=VERIFY_FORECAST,
            ok=False,
            payload={"summary": msg},
            error_type="InvalidVerificationInput",
            error_message=msg,
        )
    snap = (
        snapshot_from_forecast_result(forecast)
        if isinstance(forecast, ForecastResult)
        else forecast
    )
    result = verify_forecast(
        train_values=train,
        forecast=snap,
        train_timestamps=train_timestamps,
        actuals=None if actuals is None else _copy_float(actuals),
        residuals=None if residuals is None else _copy_float(residuals),
        spec=spec if spec is not None else VerifyForecastSpec(),
    )
    return VerificationToolEnvelope(
        tool_name=VERIFY_FORECAST,
        ok=True,
        payload=result.model_dump(mode="json"),
    )


def verify_forecast(
    *,
    train_values: np.ndarray,
    forecast: ForecastSnapshot,
    train_timestamps: pd.Series | pd.DatetimeIndex | None,
    actuals: np.ndarray | None,
    residuals: np.ndarray | None,
    spec: VerifyForecastSpec,
) -> VerifyForecastResult:
    yhat = _copy_float(forecast.yhat)
    lower = _copy_float(forecast.lower)
    upper = _copy_float(forecast.upper)
    train = np.asarray(train_values, dtype=float).copy()
    period = spec.seasonal_period
    if period is None:
        period = period_from_frequency(forecast.frequency)
    nominal = spec.nominal_coverage
    if nominal is None:
        nominal = forecast.interval_coverage_nominal
    if nominal is None:
        nominal = 0.95

    checks = [
        _check_invalid_values(yhat, lower, upper, forecast.forecast_horizon),
        _check_forecast_bounds(yhat, lower, upper),
        _check_historical_range(train, yhat),
        _check_trend_consistency(train, yhat, train_timestamps),
        _check_seasonality_consistency(train, yhat, train_timestamps, period, forecast.frequency),
        _check_residual_diagnostics(yhat, actuals, residuals),
        _check_interval_coverage(lower, upper, actuals, nominal),
        _check_interval_width(train, lower, upper),
        _check_regime_change(train, yhat, train_timestamps),
        _check_extreme_growth(train, yhat),
    ]
    overall = aggregate_check_results(checks)
    n_fail = sum(1 for item in checks if item.result == "FAIL")
    n_warn = sum(1 for item in checks if item.result == "WARN")
    n_pass = sum(1 for item in checks if item.result == "PASS")
    limitations = [
        "Checks challenge the artifact; they do not produce a replacement forecast.",
        "PASS means the check did not falsify the artifact, not that the forecast is true.",
        "Coverage and residual checks require holdout actuals or supplied residuals.",
        "Source arrays were copied and were not modified.",
    ]
    summary = (
        f"overall={overall}; fail={n_fail}; warn={n_warn}; pass={n_pass}. "
        "Deterministic evidence is not optional."
    )
    return VerifyForecastResult(
        overall_result=overall,
        n_fail=n_fail,
        n_warn=n_warn,
        n_pass=n_pass,
        checks=checks,
        limitations=limitations,
        challenged=overall != "PASS",
        summary=summary,
    )


def aggregate_check_results(checks: list[VerificationCheck]) -> CheckResult:
    if any(item.result == "FAIL" for item in checks):
        return "FAIL"
    if any(item.result == "WARN" for item in checks):
        return "WARN"
    return "PASS"


def _check_invalid_values(
    yhat: np.ndarray,
    lower: np.ndarray,
    upper: np.ndarray,
    horizon: int,
) -> VerificationCheck:
    n_nan = int(
        (~np.isfinite(yhat)).sum() + (~np.isfinite(lower)).sum() + (~np.isfinite(upper)).sum()
    )
    lengths = {
        "yhat": int(yhat.size),
        "lower": int(lower.size),
        "upper": int(upper.size),
        "horizon": int(horizon),
    }
    aligned = yhat.size == lower.size == upper.size == horizon and horizon >= 1
    empty = yhat.size == 0 or horizon < 1
    failed = n_nan > 0 or (not aligned) or empty
    if failed:
        explanation = f"Missing or invalid forecast values: non-finite={n_nan}, lengths={lengths}."
        result: CheckResult = "FAIL"
        severity: Severity = "high"
    else:
        explanation = "All forecast point and interval values are finite and horizon-aligned."
        result = "PASS"
        severity = "low"
    return VerificationCheck(
        check_id=CHECK_INVALID_VALUES,
        name="missing/invalid forecast values",
        result=result,
        severity=severity,
        explanation=explanation,
        evidence={"n_non_finite": n_nan, "lengths": lengths, "aligned": aligned},
    )


def _check_forecast_bounds(
    yhat: np.ndarray,
    lower: np.ndarray,
    upper: np.ndarray,
) -> VerificationCheck:
    n = min(yhat.size, lower.size, upper.size)
    n_inverted = 0
    n_outside = 0
    for i in range(n):
        lo, mid, hi = lower[i], yhat[i], upper[i]
        if np.isfinite(lo) and np.isfinite(hi) and lo > hi:
            n_inverted += 1
        if np.isfinite(lo) and np.isfinite(mid) and mid < lo:
            n_outside += 1
        if np.isfinite(hi) and np.isfinite(mid) and mid > hi:
            n_outside += 1
    failed = n_inverted > 0 or n_outside > 0
    if failed:
        explanation = (
            f"Forecast bounds violated: {n_inverted} inverted interval(s), "
            f"{n_outside} yhat value(s) outside [lower, upper]."
        )
        result: CheckResult = "FAIL"
        severity: Severity = "high"
    else:
        explanation = (
            "Every finite yhat lies inside its [lower, upper] interval; bounds are ordered."
        )
        result = "PASS"
        severity = "low"
    return VerificationCheck(
        check_id=CHECK_FORECAST_BOUNDS,
        name="forecast bounds",
        result=result,
        severity=severity,
        explanation=explanation,
        evidence={
            "n_inverted": n_inverted,
            "n_yhat_outside_interval": n_outside,
            "n_compared": n,
        },
    )


def _check_historical_range(train: np.ndarray, yhat: np.ndarray) -> VerificationCheck:
    hist = train[np.isfinite(train)]
    fc = yhat[np.isfinite(yhat)]
    if hist.size == 0 or fc.size == 0:
        return _na(
            CHECK_HISTORICAL_RANGE,
            "historical-range comparison",
            "Historical-range comparison is not applicable: no finite training or forecast values.",
        )
    hist_min = float(np.min(hist))
    hist_max = float(np.max(hist))
    iqr = _iqr(hist)
    scale = iqr if iqr > 0 else float(np.std(hist, ddof=1) if hist.size > 1 else 0.0)
    fail_pad = _RANGE_FAIL_IQR * scale
    n_outside = int(np.sum((fc < hist_min) | (fc > hist_max)))
    if scale > 0:
        n_extreme = int(np.sum((fc < hist_min - fail_pad) | (fc > hist_max + fail_pad)))
    elif n_outside:
        n_extreme = n_outside
    else:
        n_extreme = 0
    fc_min = float(np.min(fc))
    fc_max = float(np.max(fc))
    evidence = {
        "hist_min": hist_min,
        "hist_max": hist_max,
        "forecast_min": fc_min,
        "forecast_max": fc_max,
        "n_outside_hist_minmax": n_outside,
        "n_extreme": n_extreme,
        "scale": scale,
        "fail_pad": fail_pad,
    }
    if n_extreme > 0:
        return VerificationCheck(
            check_id=CHECK_HISTORICAL_RANGE,
            name="historical-range comparison",
            result="FAIL",
            severity="high",
            explanation=(
                f"{n_extreme} forecast value(s) lie far outside the training range "
                f"[{hist_min:.6g}, {hist_max:.6g}]."
            ),
            evidence=evidence,
        )
    if n_outside > 0:
        return VerificationCheck(
            check_id=CHECK_HISTORICAL_RANGE,
            name="historical-range comparison",
            result="WARN",
            severity="medium",
            explanation=(
                f"{n_outside} forecast value(s) fall outside the observed training min/max."
            ),
            evidence=evidence,
        )
    return VerificationCheck(
        check_id=CHECK_HISTORICAL_RANGE,
        name="historical-range comparison",
        result="PASS",
        severity="low",
        explanation="Forecast values stay within the observed training min/max.",
        evidence=evidence,
    )


def _check_trend_consistency(
    train: np.ndarray,
    yhat: np.ndarray,
    timestamps: pd.Series | pd.DatetimeIndex | None,
) -> VerificationCheck:
    hist = train[np.isfinite(train)]
    fc = yhat[np.isfinite(yhat)]
    if hist.size < 3 or fc.size < 2:
        return _na(
            CHECK_TREND_CONSISTENCY,
            "trend consistency",
            "Trend consistency is not applicable: insufficient finite points.",
        )
    screen = diagnose_trend(train, timestamps)
    hist_slope = _ols_slope(hist)
    fc_slope = _ols_slope(fc)
    hist_std = float(np.std(hist, ddof=1)) if hist.size > 1 else 0.0
    material = hist_std / max(float(hist.size), 1.0)
    opposite = (
        np.isfinite(hist_slope)
        and np.isfinite(fc_slope)
        and hist_slope * fc_slope < 0
        and abs(fc_slope) > material
        and abs(hist_slope) > material
    )
    evidence = {
        "hist_slope": hist_slope,
        "forecast_slope": fc_slope,
        "trend_detected": screen.detected,
        "spearman_rho": screen.evidence.statistic,
        "material_slope": material,
    }
    if screen.detected and opposite:
        return VerificationCheck(
            check_id=CHECK_TREND_CONSISTENCY,
            name="trend consistency",
            result="FAIL",
            severity="high",
            explanation=(
                "History shows a detected trend but the forecast slope has the opposite sign."
            ),
            evidence=evidence,
        )
    hist_mag = max(abs(hist_slope), material) if np.isfinite(hist_slope) else material
    if screen.detected and np.isfinite(fc_slope) and abs(fc_slope) < _TREND_SLOPE_FRAC * hist_mag:
        return VerificationCheck(
            check_id=CHECK_TREND_CONSISTENCY,
            name="trend consistency",
            result="WARN",
            severity="medium",
            explanation="A historical trend was detected but the forecast slope is near flat.",
            evidence=evidence,
        )
    return VerificationCheck(
        check_id=CHECK_TREND_CONSISTENCY,
        name="trend consistency",
        result="PASS",
        severity="low",
        explanation="Forecast slope does not contradict the historical trend screen.",
        evidence=evidence,
    )


def _check_seasonality_consistency(
    train: np.ndarray,
    yhat: np.ndarray,
    timestamps: pd.Series | pd.DatetimeIndex | None,
    period: int | None,
    frequency: str,
) -> VerificationCheck:
    hist = train[np.isfinite(train)]
    fc = yhat[np.isfinite(yhat)]
    if period is None or period < 2:
        return _na(
            CHECK_SEASONALITY_CONSISTENCY,
            "seasonality consistency",
            "Seasonality consistency is not applicable: no seasonal period was "
            "provided or inferred.",
        )
    screen = diagnose_seasonality(train, timestamps, period=period, frequency=frequency)
    if hist.size < period or fc.size < 1:
        return _na(
            CHECK_SEASONALITY_CONSISTENCY,
            "seasonality consistency",
            "Seasonality consistency is not applicable: fewer points than one seasonal period.",
        )
    last_cycle = hist[-period:]
    n_cmp = min(int(fc.size), int(last_cycle.size), int(period))
    corr = _pearson(last_cycle[:n_cmp], fc[:n_cmp])
    evidence = {
        "period": period,
        "seasonality_detected": screen.detected,
        "pattern_correlation": corr,
        "n_compared": n_cmp,
        "acf_statistic": screen.evidence.statistic,
    }
    if screen.detected and np.isfinite(corr) and corr <= _SEASON_FAIL_CORR:
        return VerificationCheck(
            check_id=CHECK_SEASONALITY_CONSISTENCY,
            name="seasonality consistency",
            result="FAIL",
            severity="high",
            explanation=(
                "Seasonality was detected but the forecast pattern is inverted versus the "
                f"last cycle (corr={corr:.3f})."
            ),
            evidence=evidence,
        )
    if screen.detected and (not np.isfinite(corr) or corr < _SEASON_WARN_CORR):
        return VerificationCheck(
            check_id=CHECK_SEASONALITY_CONSISTENCY,
            name="seasonality consistency",
            result="WARN",
            severity="medium",
            explanation=(
                "Seasonality was detected but the forecast pattern is weakly aligned with "
                "the last cycle."
            ),
            evidence=evidence,
        )
    return VerificationCheck(
        check_id=CHECK_SEASONALITY_CONSISTENCY,
        name="seasonality consistency",
        result="PASS",
        severity="low",
        explanation="Forecast seasonal pattern does not contradict the seasonality screen.",
        evidence=evidence,
    )


def _check_residual_diagnostics(
    yhat: np.ndarray,
    actuals: np.ndarray | None,
    residuals: np.ndarray | None,
) -> VerificationCheck:
    resid: np.ndarray | None = None
    source = "none"
    if actuals is not None:
        if actuals.size != yhat.size:
            return VerificationCheck(
                check_id=CHECK_RESIDUAL_DIAGNOSTICS,
                name="residual diagnostics",
                result="FAIL",
                severity="high",
                explanation=(
                    f"Residual diagnostics failed: actuals length {actuals.size} != "
                    f"yhat length {yhat.size}."
                ),
                evidence={"actuals_length": int(actuals.size), "yhat_length": int(yhat.size)},
            )
        resid = actuals - yhat
        source = "holdout_actuals_minus_yhat"
    elif residuals is not None:
        resid = np.asarray(residuals, dtype=float).copy()
        source = "supplied_residuals"
    if resid is None:
        return _na(
            CHECK_RESIDUAL_DIAGNOSTICS,
            "residual diagnostics",
            "Residual diagnostics are not applicable: no holdout actuals or "
            "residuals were supplied.",
        )
    finite = resid[np.isfinite(resid)]
    if finite.size < 2:
        return _na(
            CHECK_RESIDUAL_DIAGNOSTICS,
            "residual diagnostics",
            "Residual diagnostics are not applicable: fewer than two finite residuals.",
        )
    mean = float(np.mean(finite))
    std = float(np.std(finite, ddof=1))
    se = std / np.sqrt(finite.size) if std > 0 else 0.0
    z = abs(mean / se) if se > 0 else (abs(mean) if mean != 0 else 0.0)
    acf1 = _lag1_acf(finite)
    evidence = {
        "source": source,
        "n_finite": int(finite.size),
        "mean": mean,
        "std": std,
        "bias_z": z,
        "lag1_acf": acf1,
    }
    if z >= _BIAS_FAIL_Z:
        return VerificationCheck(
            check_id=CHECK_RESIDUAL_DIAGNOSTICS,
            name="residual diagnostics",
            result="FAIL",
            severity="high",
            explanation=f"Residuals show strong bias (mean z={z:.2f}).",
            evidence=evidence,
        )
    if z >= _BIAS_WARN_Z or (np.isfinite(acf1) and abs(acf1) >= _ACF_WARN):
        why: list[str] = []
        if z >= _BIAS_WARN_Z:
            why.append(f"mean z={z:.2f}")
        if np.isfinite(acf1) and abs(acf1) >= _ACF_WARN:
            why.append(f"lag-1 ACF={acf1:.2f}")
        return VerificationCheck(
            check_id=CHECK_RESIDUAL_DIAGNOSTICS,
            name="residual diagnostics",
            result="WARN",
            severity="medium",
            explanation="Residual structure remains: " + ", ".join(why) + ".",
            evidence=evidence,
        )
    return VerificationCheck(
        check_id=CHECK_RESIDUAL_DIAGNOSTICS,
        name="residual diagnostics",
        result="PASS",
        severity="low",
        explanation="Residual mean and lag-1 autocorrelation are within configured limits.",
        evidence=evidence,
    )


def _check_interval_coverage(
    lower: np.ndarray,
    upper: np.ndarray,
    actuals: np.ndarray | None,
    nominal: float,
) -> VerificationCheck:
    if actuals is None:
        return _na(
            CHECK_INTERVAL_COVERAGE,
            "prediction interval coverage",
            "Interval coverage is not evaluable without holdout actuals.",
        )
    if actuals.size != lower.size or actuals.size != upper.size:
        return VerificationCheck(
            check_id=CHECK_INTERVAL_COVERAGE,
            name="prediction interval coverage",
            result="FAIL",
            severity="high",
            explanation=(
                "Holdout length does not match interval length; coverage cannot be trusted."
            ),
            evidence={
                "actuals_length": int(actuals.size),
                "lower_length": int(lower.size),
                "upper_length": int(upper.size),
            },
        )
    try:
        emp = interval_coverage(actuals, lower, upper)
    except IntervalOrderError as exc:
        return VerificationCheck(
            check_id=CHECK_INTERVAL_COVERAGE,
            name="prediction interval coverage",
            result="FAIL",
            severity="high",
            explanation=f"Coverage cannot be scored: {exc}",
            evidence={"nominal_coverage": nominal},
        )
    gap = (nominal - emp) if np.isfinite(emp) else None
    evidence = {
        "nominal_coverage": nominal,
        "empirical_coverage": None if not np.isfinite(emp) else float(emp),
        "gap": gap,
        "n_holdout": int(actuals.size),
    }
    if not np.isfinite(emp):
        return _na(
            CHECK_INTERVAL_COVERAGE,
            "prediction interval coverage",
            "Interval coverage is undefined: no finite holdout/interval triples.",
        )
    if gap is not None and gap >= _COVERAGE_FAIL_GAP:
        return VerificationCheck(
            check_id=CHECK_INTERVAL_COVERAGE,
            name="prediction interval coverage",
            result="FAIL",
            severity="high",
            explanation=(
                f"Empirical coverage {emp:.3f} is well below nominal {nominal:.3f} (gap={gap:.3f})."
            ),
            evidence=evidence,
        )
    if gap is not None and gap >= _COVERAGE_WARN_GAP:
        return VerificationCheck(
            check_id=CHECK_INTERVAL_COVERAGE,
            name="prediction interval coverage",
            result="WARN",
            severity="medium",
            explanation=(
                f"Empirical coverage {emp:.3f} is below nominal {nominal:.3f} (gap={gap:.3f})."
            ),
            evidence=evidence,
        )
    return VerificationCheck(
        check_id=CHECK_INTERVAL_COVERAGE,
        name="prediction interval coverage",
        result="PASS",
        severity="low",
        explanation=(
            f"Empirical coverage {emp:.3f} is within {_COVERAGE_WARN_GAP:.2f} of "
            f"nominal {nominal:.3f}."
        ),
        evidence=evidence,
    )


def _check_interval_width(
    train: np.ndarray,
    lower: np.ndarray,
    upper: np.ndarray,
) -> VerificationCheck:
    hist = train[np.isfinite(train)]
    try:
        mean_w = interval_width(lower, upper)
    except IntervalOrderError as exc:
        return VerificationCheck(
            check_id=CHECK_INTERVAL_WIDTH,
            name="interval width",
            result="FAIL",
            severity="high",
            explanation=f"Interval width cannot be scored: {exc}",
            evidence={},
        )
    if not np.isfinite(mean_w):
        return VerificationCheck(
            check_id=CHECK_INTERVAL_WIDTH,
            name="interval width",
            result="FAIL",
            severity="high",
            explanation="Interval width is undefined: no finite lower/upper pairs.",
            evidence={"mean_width": None},
        )
    iqr = _iqr(hist) if hist.size else 0.0
    std = float(np.std(hist, ddof=1)) if hist.size > 1 else 0.0
    scale = iqr if iqr > 0 else std
    ratio = (mean_w / scale) if scale > 0 else None
    evidence = {"mean_width": float(mean_w), "hist_scale": scale, "width_to_scale": ratio}
    if scale > 0 and mean_w == 0.0:
        return VerificationCheck(
            check_id=CHECK_INTERVAL_WIDTH,
            name="interval width",
            result="FAIL",
            severity="high",
            explanation="Prediction intervals have zero width on a non-constant training series.",
            evidence=evidence,
        )
    if ratio is not None and ratio >= _WIDTH_FAIL_MULT:
        return VerificationCheck(
            check_id=CHECK_INTERVAL_WIDTH,
            name="interval width",
            result="FAIL",
            severity="high",
            explanation=(
                f"Mean interval width is {ratio:.1f}× the historical scale (vacuous intervals)."
            ),
            evidence=evidence,
        )
    if ratio is not None and ratio >= _WIDTH_WARN_MULT:
        return VerificationCheck(
            check_id=CHECK_INTERVAL_WIDTH,
            name="interval width",
            result="WARN",
            severity="medium",
            explanation=f"Mean interval width is {ratio:.1f}× the historical scale.",
            evidence=evidence,
        )
    if ratio is not None and ratio <= _WIDTH_TIGHT_FRAC and scale > 0:
        return VerificationCheck(
            check_id=CHECK_INTERVAL_WIDTH,
            name="interval width",
            result="WARN",
            severity="medium",
            explanation="Prediction intervals are extremely tight relative to historical scale.",
            evidence=evidence,
        )
    return VerificationCheck(
        check_id=CHECK_INTERVAL_WIDTH,
        name="interval width",
        result="PASS",
        severity="low",
        explanation="Mean interval width is within configured limits relative to historical scale.",
        evidence=evidence,
    )


def _check_regime_change(
    train: np.ndarray,
    yhat: np.ndarray,
    timestamps: pd.Series | pd.DatetimeIndex | None,
) -> VerificationCheck:
    hist = train[np.isfinite(train)]
    fc = yhat[np.isfinite(yhat)]
    screen = diagnose_structural_breaks(train, timestamps)
    evidence: JsonObject = {
        "break_detected": screen.detected,
        "break_statistic": screen.evidence.statistic,
        "n_flagged": screen.evidence.n_flagged,
    }
    if not screen.detected:
        return VerificationCheck(
            check_id=CHECK_REGIME_CHANGE,
            name="regime-change risk",
            result="PASS",
            severity="low",
            explanation="No structural-break flag on the training series.",
            evidence=evidence,
        )
    if hist.size < 8 or fc.size == 0:
        return VerificationCheck(
            check_id=CHECK_REGIME_CHANGE,
            name="regime-change risk",
            result="WARN",
            severity="high",
            explanation=(
                "A structural-break flag is present. A single global forecast may be miscalibrated."
            ),
            evidence=evidence,
        )
    split = max(int(hist.size * 0.25), 1)
    early = float(np.mean(hist[:split]))
    late = float(np.mean(hist[-split:]))
    fc_mean = float(np.mean(fc))
    dist_early = abs(fc_mean - early)
    dist_late = abs(fc_mean - late)
    evidence.update(
        {
            "early_mean": early,
            "late_mean": late,
            "forecast_mean": fc_mean,
            "dist_early": dist_early,
            "dist_late": dist_late,
        }
    )
    late_scale = float(np.std(hist[-split:], ddof=1)) if split > 1 else 0.0
    stuck_on_old = dist_late > dist_early * 1.5 and dist_late > max(0.5 * late_scale, 1e-9)
    if stuck_on_old:
        return VerificationCheck(
            check_id=CHECK_REGIME_CHANGE,
            name="regime-change risk",
            result="FAIL",
            severity="high",
            explanation=(
                "A mean-shift was detected and the forecast is closer to the early-regime mean "
                "than to the recent mean."
            ),
            evidence=evidence,
        )
    return VerificationCheck(
        check_id=CHECK_REGIME_CHANGE,
        name="regime-change risk",
        result="WARN",
        severity="high",
        explanation=(
            "A structural-break flag is present. The forecast was not treated as validated "
            "across the regime change."
        ),
        evidence=evidence,
    )


def _check_extreme_growth(train: np.ndarray, yhat: np.ndarray) -> VerificationCheck:
    hist = train[np.isfinite(train)]
    fc = yhat[np.isfinite(yhat)]
    if hist.size == 0 or fc.size == 0:
        return _na(
            CHECK_EXTREME_GROWTH,
            "extreme forecast growth",
            "Extreme-growth check is not applicable: no finite values.",
        )
    peak_hist = float(np.max(np.abs(hist)))
    peak_fc = float(np.max(np.abs(fc)))
    denom = peak_hist if peak_hist > 0 else _iqr(hist)
    ratio = peak_fc / denom if denom > 0 else (peak_fc if peak_fc > 0 else 1.0)
    y_last = float(hist[-1])
    end_ratio = None
    if y_last != 0 and np.isfinite(y_last):
        end_ratio = abs(float(fc[-1]) / y_last)
    evidence = {
        "peak_hist_abs": peak_hist,
        "peak_forecast_abs": peak_fc,
        "peak_ratio": ratio,
        "end_vs_last_ratio": end_ratio,
    }
    fail_hit = ratio >= _GROWTH_FAIL or (end_ratio is not None and end_ratio >= _GROWTH_FAIL)
    warn_hit = ratio >= _GROWTH_WARN or (end_ratio is not None and end_ratio >= _GROWTH_WARN)
    if fail_hit:
        extra = f", end/last={end_ratio:.2f}" if end_ratio is not None else ""
        return VerificationCheck(
            check_id=CHECK_EXTREME_GROWTH,
            name="extreme forecast growth",
            result="FAIL",
            severity="high",
            explanation=(
                f"Forecast magnitude is extreme versus history (peak ratio={ratio:.2f}{extra})."
            ),
            evidence=evidence,
        )
    if warn_hit:
        return VerificationCheck(
            check_id=CHECK_EXTREME_GROWTH,
            name="extreme forecast growth",
            result="WARN",
            severity="medium",
            explanation=f"Forecast magnitude is large versus history (peak ratio={ratio:.2f}).",
            evidence=evidence,
        )
    return VerificationCheck(
        check_id=CHECK_EXTREME_GROWTH,
        name="extreme forecast growth",
        result="PASS",
        severity="low",
        explanation="Forecast magnitude is not extreme relative to history.",
        evidence=evidence,
    )


def _na(check_id: str, name: str, explanation: str) -> VerificationCheck:
    return VerificationCheck(
        check_id=check_id,
        name=name,
        result="WARN",
        severity="medium",
        explanation=explanation,
        evidence={"applicable": False},
        applicable=False,
    )


def _copy_float(values: pd.Series | np.ndarray | list[float]) -> np.ndarray:
    return np.asarray(values, dtype=float).copy()


def _iqr(values: np.ndarray) -> float:
    if values.size < 2:
        return 0.0
    q1 = float(np.percentile(values, 25))
    q3 = float(np.percentile(values, 75))
    return max(q3 - q1, 0.0)


def _ols_slope(values: np.ndarray) -> float:
    if values.size < 2:
        return float("nan")
    order = np.arange(values.size, dtype=float)
    if float(np.std(order)) == 0.0:
        return 0.0
    return float(np.polyfit(order, values, 1)[0])


def _pearson(left: np.ndarray, right: np.ndarray) -> float:
    if left.size < 2 or right.size < 2 or left.size != right.size:
        return float("nan")
    if float(np.std(left)) == 0.0 or float(np.std(right)) == 0.0:
        return float("nan")
    corr = float(np.corrcoef(left, right)[0, 1])
    if not np.isfinite(corr):
        return float("nan")
    return corr


def _lag1_acf(values: np.ndarray) -> float:
    if values.size < 5:
        return float("nan")
    centered = values - float(np.mean(values))
    denom = float(np.dot(centered, centered))
    if denom == 0.0:
        return float("nan")
    return float(np.dot(centered[1:], centered[:-1]) / denom)
