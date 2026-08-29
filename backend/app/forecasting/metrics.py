"""Forecast accuracy metrics. Point scores and interval scores are computed separately.

NaNs are omitted pairwise (never filled). Empty or fully-invalid input yields NaN,
not a silent zero. These functions do not mutate caller arrays.
"""

from __future__ import annotations

import numpy as np

from app.forecasting.intervals import assert_interval_order, coverage_to_alpha

_SMAPE_BOTH_ZERO = 0.0


def mae(actual: np.ndarray | list[float], predicted: np.ndarray | list[float]) -> float:
    y, yhat, mask = _pair(actual, predicted)
    if not np.any(mask):
        return np.nan
    return float(np.mean(np.abs(y[mask] - yhat[mask])))


def rmse(actual: np.ndarray | list[float], predicted: np.ndarray | list[float]) -> float:
    y, yhat, mask = _pair(actual, predicted)
    if not np.any(mask):
        return np.nan
    err = y[mask] - yhat[mask]
    return float(np.sqrt(np.mean(err * err)))


def smape(actual: np.ndarray | list[float], predicted: np.ndarray | list[float]) -> float:
    """Symmetric MAPE in percent, range 0–200.

    Term is ``100 * 2 * |y-ŷ| / (|y|+|ŷ|)``. If both y and ŷ are 0, the term is 0
    (not undefined). Negative values are allowed; denominators use absolute values.
    """
    y, yhat, mask = _pair(actual, predicted)
    if not np.any(mask):
        return np.nan
    yv = y[mask]
    pv = yhat[mask]
    denom = np.abs(yv) + np.abs(pv)
    term = np.empty_like(denom)
    both_zero = denom == 0
    term[both_zero] = _SMAPE_BOTH_ZERO
    safe = ~both_zero
    term[safe] = 2.0 * np.abs(yv[safe] - pv[safe]) / denom[safe]
    return float(100.0 * np.mean(term))


def wmape(actual: np.ndarray | list[float], predicted: np.ndarray | list[float]) -> float:
    """Weighted MAPE in percent: ``100 * sum(|y-ŷ|) / sum(|y|)``.

    If all finite actuals are 0, the denominator is 0 and the result is NaN
    (not Inf). Zeros in y with nonzero ŷ still contribute to the numerator.
    """
    y, yhat, mask = _pair(actual, predicted)
    if not np.any(mask):
        return np.nan
    yv = y[mask]
    pv = yhat[mask]
    denom = float(np.sum(np.abs(yv)))
    if denom == 0.0:
        return np.nan
    return float(100.0 * np.sum(np.abs(yv - pv)) / denom)


def mase(
    actual: np.ndarray | list[float],
    predicted: np.ndarray | list[float],
    insample: np.ndarray | list[float],
    *,
    seasonality_period: int = 1,
) -> float:
    """MAE scaled by in-sample seasonal-naive MAE (Hyndman & Koehler).

    ``seasonality_period`` is the seasonal naive lag (1 = non-seasonal naive).
    If the in-sample scale is 0 (e.g. constant train series), returns NaN.
    ``insample`` is not modified and is not used as future data.
    """
    if seasonality_period < 1:
        msg = "seasonality_period must be >= 1"
        raise ValueError(msg)
    y, yhat, mask = _pair(actual, predicted)
    if not np.any(mask):
        return np.nan
    scale = _naive_mae_scale(insample, seasonality_period)
    if not np.isfinite(scale) or scale == 0.0:
        return np.nan
    return float(np.mean(np.abs(y[mask] - yhat[mask])) / scale)


def interval_score(
    actual: np.ndarray | list[float],
    lower: np.ndarray | list[float],
    upper: np.ndarray | list[float],
    *,
    coverage: float,
) -> float:
    """Mean Gneiting–Raftery interval score for a central ``coverage`` interval.

    ``IS_α = (u-l) + (2/α)(l-y)_+ + (2/α)(y-u)_+`` with ``α = 1-coverage``.
    Lower > upper (finite) raises IntervalOrderError. Point accuracy is not mixed in.
    """
    y, lo, hi, mask = _triple(actual, lower, upper)
    assert_interval_order(lo, hi)
    if not np.any(mask):
        return np.nan
    alpha = coverage_to_alpha(coverage)
    yv, lv, uv = y[mask], lo[mask], hi[mask]
    width = uv - lv
    below = np.maximum(lv - yv, 0.0)
    above = np.maximum(yv - uv, 0.0)
    scores = width + (2.0 / alpha) * below + (2.0 / alpha) * above
    return float(np.mean(scores))


def wis(
    actual: np.ndarray | list[float],
    yhat: np.ndarray | list[float],
    lower: np.ndarray | list[float],
    upper: np.ndarray | list[float],
    *,
    coverage: float,
) -> float:
    """Mean Weighted Interval Score for one central interval plus a median (Bracher et al.).

    Uses ``yhat`` as the median forecast. For K=1 interval:

    ``WIS = 1/(K+0.5) * (0.5*|y-m| + (α/2)*IS_α)`` with ``α = 1-coverage``.

    This is the evaluation primary metric building block; it is not MAPE.
    """
    y, m, mask_p = _pair(actual, yhat)
    y2, lo, hi, mask_i = _triple(actual, lower, upper)
    assert_interval_order(lo, hi)
    mask = mask_p & mask_i
    if not np.any(mask):
        return np.nan
    alpha = coverage_to_alpha(coverage)
    yv = y[mask]
    mv = m[mask]
    lv = lo[mask]
    uv = hi[mask]
    is_alpha = (
        (uv - lv)
        + (2.0 / alpha) * np.maximum(lv - yv, 0.0)
        + (2.0 / alpha) * np.maximum(yv - uv, 0.0)
    )
    k = 1.0
    wis_t = (1.0 / (k + 0.5)) * (0.5 * np.abs(yv - mv) + (alpha / 2.0) * is_alpha)
    return float(np.mean(wis_t))


def interval_coverage(
    actual: np.ndarray | list[float],
    lower: np.ndarray | list[float],
    upper: np.ndarray | list[float],
) -> float:
    """Empirical coverage: fraction of finite triples with lower <= y <= upper."""
    y, lo, hi, mask = _triple(actual, lower, upper)
    assert_interval_order(lo, hi)
    if not np.any(mask):
        return np.nan
    inside = (lo[mask] <= y[mask]) & (y[mask] <= hi[mask])
    return float(np.mean(inside))


def interval_width(
    lower: np.ndarray | list[float],
    upper: np.ndarray | list[float],
) -> float:
    """Mean (upper - lower) over pairs where both bounds are finite."""
    lo = np.asarray(lower, dtype=float).copy()
    hi = np.asarray(upper, dtype=float).copy()
    if lo.shape != hi.shape:
        msg = "lower and upper must have the same shape"
        raise ValueError(msg)
    assert_interval_order(lo, hi)
    mask = np.isfinite(lo) & np.isfinite(hi)
    if not np.any(mask):
        return np.nan
    return float(np.mean(hi[mask] - lo[mask]))


def _pair(
    actual: np.ndarray | list[float],
    predicted: np.ndarray | list[float],
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    y = np.asarray(actual, dtype=float).copy()
    yhat = np.asarray(predicted, dtype=float).copy()
    if y.shape != yhat.shape:
        msg = f"actual shape {y.shape} != predicted shape {yhat.shape}"
        raise ValueError(msg)
    mask = np.isfinite(y) & np.isfinite(yhat)
    return y, yhat, mask


def _triple(
    actual: np.ndarray | list[float],
    lower: np.ndarray | list[float],
    upper: np.ndarray | list[float],
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    y = np.asarray(actual, dtype=float).copy()
    lo = np.asarray(lower, dtype=float).copy()
    hi = np.asarray(upper, dtype=float).copy()
    if not (y.shape == lo.shape == hi.shape):
        msg = f"actual/lower/upper shapes differ: {y.shape}, {lo.shape}, {hi.shape}"
        raise ValueError(msg)
    mask = np.isfinite(y) & np.isfinite(lo) & np.isfinite(hi)
    return y, lo, hi, mask


def _naive_mae_scale(insample: np.ndarray | list[float], period: int) -> float:
    train = np.asarray(insample, dtype=float).copy()
    if train.size < period + 1:
        return np.nan
    diffs: list[float] = []
    for t in range(period, train.size):
        a = train[t]
        b = train[t - period]
        if np.isfinite(a) and np.isfinite(b):
            diffs.append(abs(float(a) - float(b)))
    if not diffs:
        return np.nan
    return float(np.mean(diffs))
