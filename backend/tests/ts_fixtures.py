"""Shared synthetic series for baseline-model unit tests. Not evaluation data."""

from __future__ import annotations

import numpy as np
import pandas as pd


def daily_index(n: int, *, start: str = "2020-01-01") -> pd.DatetimeIndex:
    return pd.date_range(start, periods=n, freq="D", tz="UTC")


def trend_seasonal(n: int, *, period: int = 7) -> np.ndarray:
    t = np.arange(n, dtype=float)
    return 10.0 + 0.2 * t + 3.0 * np.sin(2.0 * np.pi * t / period)
