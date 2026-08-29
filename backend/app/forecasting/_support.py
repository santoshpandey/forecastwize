"""Shared training copies and residual intervals for baseline models. No HTTP/LLM."""

from __future__ import annotations

from statistics import NormalDist

import numpy as np
import pandas as pd

from app.forecasting.base import (
    ForecastInterfaceError,
    ModelNotFittedError,
    TrainingRange,
    _as_datetime_list,
)


def copy_training(
    timestamps: pd.Series | pd.DatetimeIndex,
    values: pd.Series | np.ndarray,
    *,
    frequency: str,
) -> tuple[pd.DatetimeIndex, np.ndarray]:
    if not frequency or not str(frequency).strip():
        msg = "frequency must be a non-empty explicit alias"
        raise ForecastInterfaceError(msg)
    index = pd.DatetimeIndex(timestamps).copy()
    y = np.asarray(values, dtype=float).copy()
    if index.size != y.size:
        msg = f"timestamps length {index.size} != values length {y.size}"
        raise ForecastInterfaceError(msg)
    if y.size == 0:
        msg = "training series is empty"
        raise ForecastInterfaceError(msg)
    n_bad = int((~np.isfinite(y)).sum())
    if n_bad:
        msg = f"{n_bad} non-finite training value(s); baseline models do not impute or drop them."
        raise ForecastInterfaceError(msg)
    return index, y


def require_fitted(fitted: bool, name: str) -> None:
    if not fitted:
        raise ModelNotFittedError(f"{name} must be fit() before predict/metadata")


def require_horizon(horizon: int) -> None:
    if horizon < 1:
        msg = "horizon must be >= 1"
        raise ForecastInterfaceError(msg)


def training_range_of(index: pd.DatetimeIndex) -> TrainingRange:
    times = _as_datetime_list(index)
    return TrainingRange(start=times[0], end=times[-1])


def z_from_coverage(coverage: float) -> float:
    if not 0.0 < coverage < 1.0:
        msg = f"coverage must be in (0, 1); got {coverage}"
        raise ForecastInterfaceError(msg)
    return float(NormalDist().inv_cdf((1.0 + coverage) / 2.0))


def residual_sigma(residuals: np.ndarray) -> float:
    finite = residuals[np.isfinite(residuals)]
    if finite.size < 2:
        return 0.0
    sigma = float(np.std(finite, ddof=1))
    if not np.isfinite(sigma):
        return 0.0
    return sigma


def random_walk_intervals(
    yhat: np.ndarray,
    sigma: float,
    coverage: float,
) -> tuple[np.ndarray, np.ndarray]:
    """Naive-style intervals: ± z σ √h (error variance grows with horizon)."""
    z = z_from_coverage(coverage)
    steps = np.arange(1, yhat.size + 1, dtype=float)
    half = z * sigma * np.sqrt(steps)
    lower = yhat - half
    upper = yhat + half
    return lower, upper


def seasonal_naive_intervals(
    yhat: np.ndarray,
    sigma: float,
    coverage: float,
    period: int,
) -> tuple[np.ndarray, np.ndarray]:
    """Seasonal-naive error variance ≈ (1 + floor((h-1)/m)) σ²."""
    z = z_from_coverage(coverage)
    horizons = np.arange(1, yhat.size + 1)
    repeats = 1.0 + np.floor((horizons - 1) / period)
    half = z * sigma * np.sqrt(repeats)
    return yhat - half, yhat + half


def future_index(
    last: pd.Timestamp,
    *,
    horizon: int,
    frequency: str,
) -> pd.DatetimeIndex:
    require_horizon(horizon)
    try:
        offset = pd.tseries.frequencies.to_offset(frequency)
        start = last + offset
        return pd.date_range(start=start, periods=horizon, freq=frequency)
    except (ValueError, TypeError) as exc:
        msg = f"Cannot build forecast timestamps with frequency={frequency!r}: {exc}"
        raise ForecastInterfaceError(msg) from exc


def as_utc_last(index: pd.DatetimeIndex) -> pd.Timestamp:
    last = pd.Timestamp(index[-1])
    if last.tzinfo is None:
        return last.tz_localize("UTC")
    return last.tz_convert("UTC")
