from __future__ import annotations

from datetime import UTC, datetime

import numpy as np
import pandas as pd

from app.data.schemas import (
    DiagnosticEvidence,
    DiagnosticParam,
    DiagnosticResult,
)

_MAD_SCALE = 0.6745
_OUTLIER_MIN_N = 8
_MODIFIED_Z_THRESHOLD = 3.5
_STRONG_Z = 6.0
_ROLLING_DEFAULT_WINDOW = 7


def diagnose_outliers(
    values: pd.Series | np.ndarray,
    timestamps: pd.Series | pd.DatetimeIndex | None = None,
    *,
    modified_z_threshold: float = _MODIFIED_Z_THRESHOLD,
) -> DiagnosticResult:
    """Flag global outliers with the Iglewicz–Hoaglin modified z-score (MAD).

    Does not modify `values`. Constant series (MAD=0) cannot be scored.
    This is a screening rule, not a formal outlier test.
    """
    params = [
        DiagnosticParam(name="modified_z_threshold", value=modified_z_threshold),
        DiagnosticParam(name="min_n", value=_OUTLIER_MIN_N),
        DiagnosticParam(name="mad_scale", value=_MAD_SCALE),
    ]
    arr, times, limitations, orig_idx = finite_working_copy(values, timestamps)
    method = "modified_z_mad"
    if arr.size < _OUTLIER_MIN_N:
        limitations.append(
            f"Need at least {_OUTLIER_MIN_N} finite points; got {arr.size}. No outlier claim."
        )
        return empty_result(
            name="outliers",
            method=method,
            parameters=params,
            n_used=int(arr.size),
            limitations=limitations,
            summary="Insufficient finite points for MAD outlier screening.",
        )

    median = float(np.median(arr))
    mad = float(np.median(np.abs(arr - median)))
    params.append(DiagnosticParam(name="median", value=median))
    params.append(DiagnosticParam(name="mad", value=mad))
    if mad == 0.0:
        limitations.append(
            "MAD is 0 (constant or near-constant series); modified z-scores are undefined."
        )
        return empty_result(
            name="outliers",
            method=method,
            parameters=params,
            n_used=int(arr.size),
            limitations=limitations,
            summary="MAD is 0; outlier scores not computed.",
        )

    scores = _MAD_SCALE * (arr - median) / mad
    flag = np.abs(scores) >= modified_z_threshold
    local = np.flatnonzero(flag)
    n_flagged = int(flag.sum())
    detected = n_flagged > 0
    max_abs = float(np.max(np.abs(scores)))
    strength = _outlier_strength(max_abs, n_flagged, int(arr.size)) if detected else "none"
    confidence = _outlier_confidence(detected, int(arr.size), max_abs)

    limitations.append(
        "Modified z-score is a heuristic; heavy tails and seasonality can inflate flags."
    )
    limitations.append("Input series is not clipped, dropped, or otherwise modified.")
    return DiagnosticResult(
        name="outliers",
        detected=detected,
        method=method,
        parameters=params,
        evidence=DiagnosticEvidence(
            summary=(
                f"{n_flagged} point(s) with |modified z| >= {modified_z_threshold}."
                if detected
                else f"No points with |modified z| >= {modified_z_threshold}."
            ),
            n_points_used=int(arr.size),
            n_flagged=n_flagged,
            statistic=max_abs,
            statistic_name="max_abs_modified_z",
            timestamps=[_as_datetime(times[i]) for i in local] if times is not None else [],
            indices=[int(orig_idx[i]) for i in local],
            scores=[float(scores[i]) for i in local],
        ),
        strength=strength,  # type: ignore[arg-type]
        confidence=confidence,
        limitations=limitations,
    )


def diagnose_rolling_anomalies(
    values: pd.Series | np.ndarray,
    timestamps: pd.Series | pd.DatetimeIndex | None = None,
    *,
    window: int = _ROLLING_DEFAULT_WINDOW,
    modified_z_threshold: float = _MODIFIED_Z_THRESHOLD,
) -> DiagnosticResult:
    """Causal rolling MAD: baseline uses only past `window` points, not the candidate.

    Does not modify `values`. Does not use a centered window (that would leak future values).
    """
    params = [
        DiagnosticParam(name="window", value=window),
        DiagnosticParam(name="modified_z_threshold", value=modified_z_threshold),
        DiagnosticParam(name="causal", value=True),
    ]
    method = "causal_rolling_mad"
    arr, times, limitations, orig_idx = finite_working_copy(values, timestamps)
    if window < 5:
        limitations.append("Window < 5 is not used; rolling MAD is unstable.")
        return empty_result(
            name="rolling_anomalies",
            method=method,
            parameters=params,
            n_used=int(arr.size),
            limitations=limitations,
            summary="Window too small for conservative rolling MAD.",
        )
    if arr.size < window + 1:
        limitations.append(
            f"Need more than {window} finite points for a causal window; got {arr.size}."
        )
        return empty_result(
            name="rolling_anomalies",
            method=method,
            parameters=params,
            n_used=int(arr.size),
            limitations=limitations,
            summary="Insufficient length for causal rolling anomalies.",
        )

    scores = np.full(arr.size, np.nan)
    for i in range(window, arr.size):
        hist = arr[i - window : i]
        med = float(np.median(hist))
        mad = float(np.median(np.abs(hist - med)))
        if mad == 0.0:
            continue
        scores[i] = _MAD_SCALE * (arr[i] - med) / mad

    valid = np.isfinite(scores)
    flag = valid & (np.abs(scores) >= modified_z_threshold)
    local = np.flatnonzero(flag)
    n_flagged = int(flag.sum())
    detected = n_flagged > 0
    finite_scores = scores[valid]
    max_abs = float(np.nanmax(np.abs(finite_scores))) if finite_scores.size else 0.0
    limitations.append("The first `window` points are never flagged (no past baseline).")
    limitations.append(
        "Causal window ignores the candidate point; level shifts may flag several points."
    )
    limitations.append("Input series is not modified.")
    strength = _outlier_strength(max_abs, n_flagged, int(arr.size)) if detected else "none"
    confidence = "medium" if detected and arr.size >= window * 3 else "low"
    return DiagnosticResult(
        name="rolling_anomalies",
        detected=detected,
        method=method,
        parameters=params,
        evidence=DiagnosticEvidence(
            summary=(
                f"{n_flagged} causal rolling flag(s)."
                if detected
                else "No causal rolling MAD flags."
            ),
            n_points_used=int(arr.size),
            n_flagged=n_flagged,
            statistic=max_abs if np.isfinite(max_abs) else None,
            statistic_name="max_abs_causal_modified_z",
            timestamps=[_as_datetime(times[i]) for i in local] if times is not None else [],
            indices=[int(orig_idx[i]) for i in local],
            scores=[float(scores[i]) for i in local],
        ),
        strength=strength,  # type: ignore[arg-type]
        confidence=confidence,  # type: ignore[arg-type]
        limitations=limitations,
    )


def finite_working_copy(
    values: pd.Series | np.ndarray,
    timestamps: pd.Series | pd.DatetimeIndex | None,
) -> tuple[np.ndarray, list[pd.Timestamp] | None, list[str], np.ndarray]:
    """Copy finite observations. Never writes back into `values`."""
    arr = np.asarray(values, dtype=float).copy()
    limitations: list[str] = []
    n_nan = int(np.isnan(arr).sum())
    if n_nan:
        limitations.append(
            f"{n_nan} non-finite value(s) omitted from the working copy only; "
            "source data unchanged."
        )
    mask = np.isfinite(arr)
    orig_idx = np.flatnonzero(mask)
    finite = arr[mask]
    times: list[pd.Timestamp] | None = None
    if timestamps is not None:
        ts_index = pd.DatetimeIndex(np.asarray(timestamps))
        if len(ts_index) != len(arr):
            limitations.append("timestamps length does not match values; timestamps ignored.")
        else:
            times = [pd.Timestamp(ts_index[int(i)]) for i in orig_idx]
    return finite, times, limitations, orig_idx


def empty_result(
    *,
    name: str,
    method: str,
    parameters: list[DiagnosticParam],
    n_used: int,
    limitations: list[str],
    summary: str,
) -> DiagnosticResult:
    return DiagnosticResult(
        name=name,
        detected=False,
        method=method,
        parameters=parameters,
        evidence=DiagnosticEvidence(summary=summary, n_points_used=n_used),
        strength="none",
        confidence="low",
        limitations=limitations,
    )


def _outlier_strength(max_abs: float, n_flagged: int, n_used: int) -> str:
    if n_flagged == 0:
        return "none"
    share = n_flagged / max(n_used, 1)
    if max_abs >= _STRONG_Z and share <= 0.05:
        return "strong"
    if max_abs >= _MODIFIED_Z_THRESHOLD + 0.5:
        return "moderate"
    return "weak"


def _outlier_confidence(detected: bool, n: int, max_abs: float) -> str:
    if not detected:
        return "low"
    if n >= 15 and max_abs >= 8.0:
        return "high"
    if n >= 15 and max_abs >= _STRONG_Z:
        return "medium"
    if n >= _OUTLIER_MIN_N:
        return "medium"
    return "low"


def timestamp_to_utc_datetime(value: pd.Timestamp) -> datetime:
    ts = pd.Timestamp(value)
    if ts.tzinfo is None:
        ts = ts.tz_localize("UTC")
    else:
        ts = ts.tz_convert("UTC")
    converted = ts.to_pydatetime()
    if converted.tzinfo is None:
        return converted.replace(tzinfo=UTC)
    return converted.astimezone(UTC)


def _as_datetime(value: pd.Timestamp) -> datetime:
    return timestamp_to_utc_datetime(value)
