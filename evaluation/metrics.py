"""Evaluation scoring. Invokes forecasting metric functions; does not fork formulas."""

# ruff: noqa: E402
# isort: skip_file

from __future__ import annotations

import sys
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[1] / "backend"
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

import numpy as np
from pydantic import BaseModel, ConfigDict

from app.forecasting.metrics import (
    interval_coverage as _interval_coverage,
    interval_width as _interval_width,
    mae as _mae,
    mase as _mase,
    rmse as _rmse,
    smape as _smape,
    wis as _wis,
    wmape as _wmape,
)


def _finite_or_none(value: float) -> float | None:
    if not np.isfinite(value):
        return None
    return float(value)


class HoldoutScores(BaseModel):
    """Holdout scores. Primary is WIS. Point and interval scores stay separate."""

    model_config = ConfigDict(extra="forbid")

    wis: float | None
    smape: float | None
    wmape: float | None
    mase: float | None
    mae: float | None
    rmse: float | None
    interval_coverage: float | None
    interval_width: float | None


def score_holdout(
    actual: np.ndarray | list[float],
    yhat: np.ndarray | list[float],
    lower: np.ndarray | list[float],
    upper: np.ndarray | list[float],
    insample: np.ndarray | list[float],
    *,
    coverage: float,
    seasonality_period: int,
) -> HoldoutScores:
    """Score a holdout forecast using the shared forecasting metric module."""
    return HoldoutScores(
        wis=_finite_or_none(_wis(actual, yhat, lower, upper, coverage=coverage)),
        smape=_finite_or_none(_smape(actual, yhat)),
        wmape=_finite_or_none(_wmape(actual, yhat)),
        mase=_finite_or_none(_mase(actual, yhat, insample, seasonality_period=seasonality_period)),
        mae=_finite_or_none(_mae(actual, yhat)),
        rmse=_finite_or_none(_rmse(actual, yhat)),
        interval_coverage=_finite_or_none(_interval_coverage(actual, lower, upper)),
        interval_width=_finite_or_none(_interval_width(lower, upper)),
    )


def official_mean(values: list[float | None]) -> float | None:
    """Mean over the full list. Any missing/NaN value makes the official mean None."""
    if not values:
        return None
    nums: list[float] = []
    for item in values:
        if item is None or not np.isfinite(item):
            return None
        nums.append(float(item))
    return float(np.mean(nums))


def completed_only_mean(values: list[float | None]) -> float | None:
    """Mean of finite values only. Labeled; not the headline aggregate."""
    nums = [float(item) for item in values if item is not None and np.isfinite(item)]
    if not nums:
        return None
    return float(np.mean(nums))
