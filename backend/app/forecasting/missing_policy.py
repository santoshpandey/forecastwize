"""Named train-only missing-value policy. Never uses holdout. Never overwrites source CSV."""

from __future__ import annotations

import numpy as np
import pandas as pd
from pydantic import BaseModel, ConfigDict, Field

from app.forecasting.base import ForecastInterfaceError

LINEAR_INTERPOLATE_TRAIN = "linear_interpolate_train"


class TrainMissingPolicyRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = "missing_value_policy"
    policy: str
    n_missing_before: int = Field(ge=0)
    n_missing_after: int = Field(ge=0)
    applied: bool


def apply_linear_interpolate_train(
    timestamps: pd.Series | pd.DatetimeIndex,
    values: pd.Series | np.ndarray,
) -> tuple[np.ndarray, TrainMissingPolicyRecord | None]:
    """Fill non-finite *training* values by time interpolation.

    Holdout must not be passed in. The caller's arrays are not mutated.
    """
    index = pd.DatetimeIndex(pd.Series(timestamps).to_numpy())
    original = np.asarray(values, dtype=float)
    y = original.copy()
    if index.size != y.size:
        msg = f"timestamps length {index.size} != values length {y.size}"
        raise ForecastInterfaceError(msg)
    n_before = int((~np.isfinite(y)).sum())
    if n_before == 0:
        return y, None
    filled = pd.Series(y, index=index).interpolate(method="time", limit_direction="both")
    out = filled.to_numpy(dtype=float)
    n_after = int((~np.isfinite(out)).sum())
    if n_after:
        msg = (
            f"{LINEAR_INTERPOLATE_TRAIN} left {n_after} non-finite training value(s); "
            "refusing to invent remaining points."
        )
        raise ForecastInterfaceError(msg)
    record = TrainMissingPolicyRecord(
        policy=LINEAR_INTERPOLATE_TRAIN,
        n_missing_before=n_before,
        n_missing_after=0,
        applied=True,
    )
    return out, record
