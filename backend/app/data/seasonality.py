from __future__ import annotations

import numpy as np
import pandas as pd

from app.data.anomalies import empty_result, finite_working_copy, timestamp_to_utc_datetime
from app.data.schemas import DiagnosticEvidence, DiagnosticParam, DiagnosticResult

_TREND_MIN_N = 20
_SPEARMAN_DETECT = 0.6
_SEASON_MIN_CYCLES = 4
_ACF_MIN = 0.4


def diagnose_trend(
    values: pd.Series | np.ndarray,
    timestamps: pd.Series | pd.DatetimeIndex | None = None,
) -> DiagnosticResult:
    """Screen for monotonic trend via Spearman correlation of values vs time index.

    Not a hypothesis test (no p-value). Linear slope is reported as descriptive
    evidence only. Does not modify `values`.
    """
    method = "spearman_vs_time_index"
    params = [
        DiagnosticParam(name="min_n", value=_TREND_MIN_N),
        DiagnosticParam(name="abs_rho_threshold", value=_SPEARMAN_DETECT),
    ]
    arr, times, limitations, _orig_idx = finite_working_copy(values, timestamps)
    if arr.size < _TREND_MIN_N:
        limitations.append(
            f"Need at least {_TREND_MIN_N} finite points for a conservative "
            f"trend screen; got {arr.size}."
        )
        return empty_result(
            name="trend",
            method=method,
            parameters=params,
            n_used=int(arr.size),
            limitations=limitations,
            summary="Insufficient data for trend screening.",
        )

    order = np.arange(arr.size, dtype=float)
    rho = _spearman(order, arr)
    # Descriptive OLS slope on a copy of ranks-free values vs 0..n-1 (not used for detection).
    slope = float(np.polyfit(order, arr, 1)[0])
    params.append(DiagnosticParam(name="spearman_rho", value=rho))
    params.append(DiagnosticParam(name="ols_slope_per_step", value=slope))
    detected = abs(rho) >= _SPEARMAN_DETECT
    if abs(rho) >= 0.8:
        strength = "strong"
    elif abs(rho) >= _SPEARMAN_DETECT:
        strength = "moderate"
    elif abs(rho) >= 0.3:
        strength = "weak"
    else:
        strength = "none"
    direction = "increasing" if rho > 0 else "decreasing"
    limitations.append("Spearman vs index is not a formal test; seasonality can mimic trend.")
    limitations.append("No p-value is computed. Detection uses a high |rho| threshold only.")
    limitations.append("Input series is not detrended in place.")
    return DiagnosticResult(
        name="trend",
        detected=detected,
        method=method,
        parameters=params,
        evidence=DiagnosticEvidence(
            summary=(
                f"Spearman rho={rho:.3f} ({direction}) vs time index."
                if detected
                else f"Spearman |rho|={abs(rho):.3f} below {_SPEARMAN_DETECT} threshold."
            ),
            n_points_used=int(arr.size),
            n_flagged=0,
            statistic=rho,
            statistic_name="spearman_rho",
            timestamps=(
                [
                    timestamp_to_utc_datetime(times[0]),
                    timestamp_to_utc_datetime(times[-1]),
                ]
                if times
                else []
            ),
            indices=[],
            scores=[rho, slope],
        ),
        strength=strength,  # type: ignore[arg-type]
        confidence="medium" if detected and arr.size >= 40 else "low",
        limitations=limitations,
    )


def diagnose_seasonality(
    values: pd.Series | np.ndarray,
    timestamps: pd.Series | pd.DatetimeIndex | None = None,
    *,
    period: int | None = None,
    frequency: str | None = None,
) -> DiagnosticResult:
    """Screen seasonality via ACF at an explicit period on a linearly detrended *copy*.

    Period must be provided or inferred from `frequency` (D→7, h→24, MS/ME→12).
    Requires at least four full cycles. Does not modify `values`.
    """
    method = "acf_after_linear_detrend"
    inferred_period = period if period is not None else period_from_frequency(frequency)
    params = [
        DiagnosticParam(name="period", value=inferred_period),
        DiagnosticParam(name="frequency", value=frequency),
        DiagnosticParam(name="min_cycles", value=_SEASON_MIN_CYCLES),
        DiagnosticParam(name="acf_threshold", value=_ACF_MIN),
    ]
    arr, times, limitations, _orig_idx = finite_working_copy(values, timestamps)
    if inferred_period is None or inferred_period < 2:
        limitations.append("No seasonal period: pass period= or a known frequency (D, h, MS/ME).")
        return empty_result(
            name="seasonality",
            method=method,
            parameters=params,
            n_used=int(arr.size),
            limitations=limitations,
            summary="Seasonal period unresolved; no seasonality claim.",
        )
    min_n = inferred_period * _SEASON_MIN_CYCLES
    if arr.size < min_n:
        limitations.append(
            f"Need at least {min_n} finite points "
            f"({_SEASON_MIN_CYCLES} cycles of {inferred_period}); "
            f"got {arr.size}."
        )
        return empty_result(
            name="seasonality",
            method=method,
            parameters=params,
            n_used=int(arr.size),
            limitations=limitations,
            summary="Insufficient cycles for conservative seasonality screening.",
        )

    detrended = _linear_detrend_copy(arr)
    acf_p = _acf(detrended, inferred_period)
    bartlett = 2.0 / np.sqrt(arr.size)
    params.append(DiagnosticParam(name="acf_at_period", value=acf_p))
    params.append(DiagnosticParam(name="bartlett_2_over_sqrt_n", value=float(bartlett)))
    detected = acf_p >= max(_ACF_MIN, bartlett)
    if acf_p >= 0.7:
        strength = "strong"
    elif detected:
        strength = "moderate"
    elif acf_p >= 0.2:
        strength = "weak"
    else:
        strength = "none"
    limitations.append("Linear detrend is applied to a copy only; residual seasonality can remain.")
    limitations.append("ACF at one lag is not a full seasonal model (no STL, no calendar effects).")
    limitations.append("Input series is not modified.")
    return DiagnosticResult(
        name="seasonality",
        detected=detected,
        method=method,
        parameters=params,
        evidence=DiagnosticEvidence(
            summary=(
                f"ACF at lag {inferred_period} is {acf_p:.3f} "
                f"(threshold {max(_ACF_MIN, bartlett):.3f})."
            ),
            n_points_used=int(arr.size),
            n_flagged=0,
            statistic=acf_p,
            statistic_name=f"acf_lag_{inferred_period}",
            timestamps=(
                [
                    timestamp_to_utc_datetime(times[0]),
                    timestamp_to_utc_datetime(times[-1]),
                ]
                if times
                else []
            ),
            indices=[],
            scores=[acf_p],
        ),
        strength=strength,  # type: ignore[arg-type]
        confidence="medium" if detected and arr.size >= inferred_period * 6 else "low",
        limitations=limitations,
    )


def period_from_frequency(frequency: str | None) -> int | None:
    """Map a pandas-like alias to a candidate seasonal period. Unknown aliases return None."""
    if frequency is None:
        return None
    token = frequency.strip()
    if token in {"D", "d"}:
        return 7
    if token in {"h", "H"}:
        return 24
    if token.startswith("W"):
        return 52
    if token in {"MS", "ME", "M", "m"}:
        return 12
    return None


def _spearman(x: np.ndarray, y: np.ndarray) -> float:
    rx = pd.Series(x).rank().to_numpy()
    ry = pd.Series(y).rank().to_numpy()
    if np.std(rx) == 0 or np.std(ry) == 0:
        return 0.0
    corr = np.corrcoef(rx, ry)[0, 1]
    if not np.isfinite(corr):
        return 0.0
    return float(corr)


def _linear_detrend_copy(arr: np.ndarray) -> np.ndarray:
    order = np.arange(arr.size, dtype=float)
    coef = np.polyfit(order, arr, 1)
    return arr - np.polyval(coef, order)


def _acf(arr: np.ndarray, lag: int) -> float:
    if lag <= 0 or lag >= arr.size:
        return 0.0
    left = arr[lag:]
    right = arr[:-lag]
    if np.std(left) == 0 or np.std(right) == 0:
        return 0.0
    corr = np.corrcoef(left, right)[0, 1]
    if not np.isfinite(corr):
        return 0.0
    return float(corr)
