from __future__ import annotations

import numpy as np
import pandas as pd

from app.data.schemas import FrequencyInference

# Canonical lengths for median-delta fallback. Monthly aliases are not inferred
# from medians (month length varies); only pandas.infer_freq may return MS/ME.
_DELTA_ALIASES: tuple[tuple[float, str], ...] = (
    (3600.0, "h"),
    (86400.0, "D"),
    (604800.0, "W"),
)
_RELATIVE_TOLERANCE = 0.05


def infer_frequency(timestamps: pd.Series | pd.DatetimeIndex) -> FrequencyInference:
    """Infer a pandas offset alias and always return it explicitly.

    Method:
    1. Unique timestamps sorted ascending; ``pandas.infer_freq`` on that index.
    2. If that is None, take the minimum positive consecutive delta. If it maps
       to h/D/W (5% tolerance) and every other delta is an integer multiple of
       that step, use that alias. This recovers a regular grid when values are
       missing (gaps).
    3. Else map the median consecutive delta to h/D/W with the same tolerance
       (typical for two timestamps).
    4. Otherwise ``frequency=None``. Callers must not invent a freq.
    """
    index = _unique_sorted_index(timestamps)
    n_unique = int(len(index))
    if n_unique == 0:
        return FrequencyInference(
            frequency=None,
            method="unresolved",
            median_delta_seconds=None,
            n_unique_timestamps=0,
            confidence="low",
            notes="No timestamps available for frequency inference.",
        )

    median_seconds = _median_delta_seconds(index)

    if n_unique >= 3:
        inferred = pd.infer_freq(index)
        if inferred is not None:
            return FrequencyInference(
                frequency=str(inferred),
                method="pandas_infer_freq",
                median_delta_seconds=median_seconds,
                n_unique_timestamps=n_unique,
                confidence="high",
                notes="pandas.infer_freq on unique sorted timestamps.",
            )

    multiples_alias = _alias_from_min_delta_multiples(index)
    if multiples_alias is not None:
        return FrequencyInference(
            frequency=multiples_alias,
            method="min_delta_multiples",
            median_delta_seconds=median_seconds,
            n_unique_timestamps=n_unique,
            confidence="medium",
            notes=(
                "pandas.infer_freq was unavailable; minimum positive delta maps to "
                f"{multiples_alias} and other gaps are integer multiples of that step."
            ),
        )

    if median_seconds is not None:
        alias = _alias_from_median(median_seconds)
        if alias is not None:
            confidence = "medium" if n_unique >= 3 else "low"
            return FrequencyInference(
                frequency=alias,
                method="median_delta",
                median_delta_seconds=median_seconds,
                n_unique_timestamps=n_unique,
                confidence=confidence,
                notes=(
                    f"pandas.infer_freq was unavailable; median delta {median_seconds:.3f}s "
                    f"mapped to {alias} within {_RELATIVE_TOLERANCE:.0%} relative tolerance."
                ),
            )

    return FrequencyInference(
        frequency=None,
        method="unresolved",
        median_delta_seconds=median_seconds,
        n_unique_timestamps=n_unique,
        confidence="low",
        notes="Could not infer a regular frequency from unique timestamps.",
    )


def expected_index(start: pd.Timestamp, end: pd.Timestamp, frequency: str) -> pd.DatetimeIndex:
    """Build the regular calendar from start to end inclusive at `frequency`."""
    return pd.date_range(start=start, end=end, freq=frequency, inclusive="both")


def _unique_sorted_index(timestamps: pd.Series | pd.DatetimeIndex) -> pd.DatetimeIndex:
    if isinstance(timestamps, pd.DatetimeIndex):
        series = pd.Series(timestamps)
    else:
        series = timestamps
    cleaned = series.dropna()
    unique = pd.DatetimeIndex(pd.unique(cleaned))
    return unique.sort_values()


def _median_delta_seconds(index: pd.DatetimeIndex) -> float | None:
    if len(index) < 2:
        return None
    deltas = np.diff(index.asi8) / 1e9
    if deltas.size == 0:
        return None
    return float(np.median(deltas))


def _alias_from_min_delta_multiples(index: pd.DatetimeIndex) -> str | None:
    if len(index) < 3:
        return None
    deltas = np.diff(index.asi8) / 1e9
    positive = deltas[deltas > 0]
    if positive.size == 0:
        return None
    min_delta = float(np.min(positive))
    alias = _alias_from_median(min_delta)
    if alias is None:
        return None
    multiples = positive / min_delta
    if not np.all(np.abs(multiples - np.round(multiples)) <= _RELATIVE_TOLERANCE):
        return None
    return alias


def _alias_from_median(median_seconds: float) -> str | None:
    if median_seconds <= 0:
        return None
    for canonical, alias in _DELTA_ALIASES:
        if abs(median_seconds - canonical) / canonical <= _RELATIVE_TOLERANCE:
            return alias
    return None
