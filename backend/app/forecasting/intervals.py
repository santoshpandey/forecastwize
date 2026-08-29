"""Prediction-interval helpers. No model fitting and no mutation of inputs."""

from __future__ import annotations

import numpy as np

from app.forecasting.base import ForecastInterfaceError


class IntervalOrderError(ForecastInterfaceError):
    """Lower bound exceeds upper bound where both are finite."""


def coverage_to_alpha(coverage: float) -> float:
    """Nominal miss rate α = 1 - coverage. Coverage must be in (0, 1)."""
    if not 0.0 < coverage < 1.0:
        msg = f"coverage must be in (0, 1); got {coverage}"
        raise ForecastInterfaceError(msg)
    return 1.0 - coverage


def assert_interval_order(
    lower: np.ndarray | list[float],
    upper: np.ndarray | list[float],
) -> None:
    """Raise if any finite pair has lower > upper. NaN pairs are skipped (not reordered)."""
    lo = np.asarray(lower, dtype=float)
    hi = np.asarray(upper, dtype=float)
    if lo.shape != hi.shape:
        msg = f"lower shape {lo.shape} != upper shape {hi.shape}"
        raise ForecastInterfaceError(msg)
    both = np.isfinite(lo) & np.isfinite(hi)
    if np.any(lo[both] > hi[both]):
        bad = int(np.flatnonzero(both & (lo > hi))[0])
        msg = f"lower[{bad}]={lo[bad]} > upper[{bad}]={hi[bad]}"
        raise IntervalOrderError(msg)


def symmetric_intervals(
    yhat: np.ndarray | list[float],
    half_width: float,
) -> tuple[np.ndarray, np.ndarray]:
    """Return (lower, upper) = yhat ± half_width on a copy. Does not modify yhat."""
    point = np.asarray(yhat, dtype=float).copy()
    if not np.isfinite(half_width) or half_width < 0:
        msg = "half_width must be a finite non-negative number"
        raise ForecastInterfaceError(msg)
    lower = point - half_width
    upper = point + half_width
    return lower, upper
