from __future__ import annotations

import numpy as np
import pandas as pd

from app.data.anomalies import empty_result, finite_working_copy, timestamp_to_utc_datetime
from app.data.schemas import DiagnosticEvidence, DiagnosticParam, DiagnosticResult

_MIN_N = 30
_MIN_SEGMENT_FRAC = 0.25
_T_THRESHOLD = 4.0


def diagnose_structural_breaks(
    values: pd.Series | np.ndarray,
    timestamps: pd.Series | pd.DatetimeIndex | None = None,
    *,
    min_segment_frac: float = _MIN_SEGMENT_FRAC,
    t_threshold: float = _T_THRESHOLD,
) -> DiagnosticResult:
    """Screen for a *single* mean shift via a conservative Welch-style t scan.

    Each candidate split keeps at least `min_segment_frac` of points on both sides
    (default 25%). Detection requires |t| >= 4. This is not a Chow test, not a
    multiple-break search, and not a causal regime model. Does not modify `values`.
    """
    method = "single_mean_shift_welch_scan"
    params = [
        DiagnosticParam(name="min_n", value=_MIN_N),
        DiagnosticParam(name="min_segment_frac", value=min_segment_frac),
        DiagnosticParam(name="t_threshold", value=t_threshold),
    ]
    arr, times, limitations, orig_idx = finite_working_copy(values, timestamps)
    n = int(arr.size)
    if n < _MIN_N:
        limitations.append(f"Need at least {_MIN_N} finite points; got {n}.")
        return empty_result(
            name="structural_breaks",
            method=method,
            parameters=params,
            n_used=n,
            limitations=limitations,
            summary="Insufficient data for a conservative mean-shift scan.",
        )

    min_seg = max(int(np.ceil(min_segment_frac * n)), 8)
    if 2 * min_seg >= n:
        limitations.append("min_segment_frac leaves no interior split points.")
        return empty_result(
            name="structural_breaks",
            method=method,
            parameters=params,
            n_used=n,
            limitations=limitations,
            summary="No valid split points under the segment-length constraint.",
        )

    best_t = 0.0
    best_i = min_seg
    for i in range(min_seg, n - min_seg + 1):
        left = arr[:i]
        right = arr[i:]
        t_stat = _welch_t(left, right)
        if abs(t_stat) > abs(best_t):
            best_t = t_stat
            best_i = i

    params.append(DiagnosticParam(name="best_split_index", value=best_i))
    params.append(DiagnosticParam(name="best_t", value=best_t))
    detected = abs(best_t) >= t_threshold
    if abs(best_t) >= 6.0:
        strength = "strong"
    elif detected:
        strength = "moderate"
    elif abs(best_t) >= 2.5:
        strength = "weak"
    else:
        strength = "none"

    split_orig = int(orig_idx[best_i]) if best_i < len(orig_idx) else best_i
    split_time = [timestamp_to_utc_datetime(times[best_i])] if times is not None else []
    limitations.append("Scans mean only; variance breaks and seasonal resets are not modeled.")
    limitations.append("|t| threshold is a heuristic, not a calibrated p-value or Chow test.")
    limitations.append("A single split is reported; multiple regimes are not searched recursively.")
    limitations.append("Input series is not segmented or rewritten.")
    left_mean = float(np.mean(arr[:best_i]))
    right_mean = float(np.mean(arr[best_i:]))
    return DiagnosticResult(
        name="structural_breaks",
        detected=detected,
        method=method,
        parameters=params,
        evidence=DiagnosticEvidence(
            summary=(
                f"Largest |t|={abs(best_t):.3f} at split index {best_i} "
                f"(left mean {left_mean:.4g}, right mean {right_mean:.4g})."
            ),
            n_points_used=n,
            n_flagged=1 if detected else 0,
            statistic=best_t,
            statistic_name="welch_t_at_best_split",
            timestamps=split_time,
            indices=[split_orig],
            scores=[best_t, left_mean, right_mean],
        ),
        strength=strength,  # type: ignore[arg-type]
        confidence="medium" if detected and n >= 50 else "low",
        limitations=limitations,
    )


def _welch_t(left: np.ndarray, right: np.ndarray) -> float:
    n1 = left.size
    n2 = right.size
    if n1 < 2 or n2 < 2:
        return 0.0
    m1 = float(np.mean(left))
    m2 = float(np.mean(right))
    v1 = float(np.var(left, ddof=1))
    v2 = float(np.var(right, ddof=1))
    denom = np.sqrt(v1 / n1 + v2 / n2)
    if denom == 0.0:
        return 0.0
    return float((m1 - m2) / denom)
