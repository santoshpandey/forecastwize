from __future__ import annotations

from datetime import datetime

import pandas as pd

from app.data.frequency import expected_index, infer_frequency
from app.data.schemas import (
    CONTEXT_COL,
    EVENT_COL,
    SERIES_ID_COL,
    TIMESTAMP_COL,
    VALUE_COL,
    FrequencyInference,
    MissingPeriod,
    SeriesProfile,
    SeriesStatistics,
)


def build_profile(
    derived: pd.DataFrame,
    *,
    extra_columns: list[str],
    naive_timestamps_treated_as_utc: bool,
) -> SeriesProfile:
    """Compute structured diagnostics on a validated, sorted copy. No fills or drops."""
    if SERIES_ID_COL in derived.columns:
        freq = _frequency_across_groups(derived)
        missing = _missing_periods_by_series(derived, freq)
    else:
        freq = infer_frequency(derived[TIMESTAMP_COL])
        missing = detect_missing_periods(derived[TIMESTAMP_COL], freq, series_id=None)

    stats = compute_statistics(derived)
    has_context = CONTEXT_COL in derived.columns
    has_event = EVENT_COL in derived.columns
    return SeriesProfile(
        statistics=stats,
        frequency=freq,
        missing_periods=missing,
        has_series_id=SERIES_ID_COL in derived.columns,
        has_context=has_context,
        has_event=has_event,
        extra_columns=list(extra_columns),
        n_event_non_null=int(derived[EVENT_COL].notna().sum()) if has_event else 0,
        n_context_non_null=int(derived[CONTEXT_COL].notna().sum()) if has_context else 0,
        naive_timestamps_treated_as_utc=naive_timestamps_treated_as_utc,
    )


def compute_statistics(derived: pd.DataFrame) -> SeriesStatistics:
    values = derived[VALUE_COL]
    stamps = derived[TIMESTAMP_COL]
    non_null = values.dropna()
    n_missing = int(values.isna().sum())
    n_rows = int(len(derived))
    n_unique = int(stamps.nunique(dropna=True))
    n_duplicate_timestamps = int(n_rows - n_unique) if n_rows else 0
    start = _min_timestamp(stamps)
    end = _max_timestamp(stamps)
    std = float(non_null.std(ddof=1)) if len(non_null) >= 2 else None
    return SeriesStatistics(
        n_rows=n_rows,
        n_unique_timestamps=n_unique,
        n_missing_values=n_missing,
        n_duplicate_timestamps=n_duplicate_timestamps,
        n_zeros=int((non_null == 0).sum()),
        n_negative=int((non_null < 0).sum()),
        start=start,
        end=end,
        value_min=float(non_null.min()) if len(non_null) else None,
        value_max=float(non_null.max()) if len(non_null) else None,
        value_mean=float(non_null.mean()) if len(non_null) else None,
        value_median=float(non_null.median()) if len(non_null) else None,
        value_std_sample=std,
    )


def detect_missing_periods(
    timestamps: pd.Series,
    frequency: FrequencyInference,
    series_id: str | None,
) -> list[MissingPeriod]:
    """Find gaps on the inferred regular index. No-op if frequency is unresolved."""
    if frequency.frequency is None:
        return []
    index = pd.DatetimeIndex(pd.unique(timestamps.dropna())).sort_values()
    if len(index) < 2:
        return []
    expected = expected_index(index[0], index[-1], frequency.frequency)
    missing = expected.difference(index)
    return _group_missing(missing, frequency.frequency, series_id=series_id)


def _frequency_across_groups(derived: pd.DataFrame) -> FrequencyInference:
    inferences = [
        infer_frequency(group[TIMESTAMP_COL])
        for _, group in derived.groupby(SERIES_ID_COL, dropna=False)
    ]
    aliases = {item.frequency for item in inferences}
    if len(inferences) == 1:
        return inferences[0]
    if len(aliases) == 1 and next(iter(aliases)) is not None:
        first = inferences[0]
        return first.model_copy(
            update={
                "notes": first.notes + " All series_id groups share this frequency.",
            }
        )
    n_unique = int(derived[TIMESTAMP_COL].nunique(dropna=True))
    median = inferences[0].median_delta_seconds if inferences else None
    return FrequencyInference(
        frequency=None,
        method="unresolved",
        median_delta_seconds=median,
        n_unique_timestamps=n_unique,
        confidence="low",
        notes="series_id groups do not share a single inferred frequency.",
    )


def _missing_periods_by_series(
    derived: pd.DataFrame,
    overall: FrequencyInference,
) -> list[MissingPeriod]:
    periods: list[MissingPeriod] = []
    for series_id, group in derived.groupby(SERIES_ID_COL, dropna=False):
        freq = infer_frequency(group[TIMESTAMP_COL])
        if freq.frequency is None and overall.frequency is not None:
            freq = overall
        sid = None if pd.isna(series_id) else str(series_id)
        periods.extend(detect_missing_periods(group[TIMESTAMP_COL], freq, series_id=sid))
    return periods


def _group_missing(
    missing: pd.DatetimeIndex,
    frequency: str,
    series_id: str | None,
) -> list[MissingPeriod]:
    if len(missing) == 0:
        return []
    offset = pd.tseries.frequencies.to_offset(frequency)
    if offset is None:
        return [
            MissingPeriod(
                start=_as_datetime(ts),
                end=_as_datetime(ts),
                n_steps=1,
                series_id=series_id,
            )
            for ts in missing
        ]
    periods: list[MissingPeriod] = []
    start = missing[0]
    prev = missing[0]
    count = 1
    for ts in missing[1:]:
        if ts == prev + offset:
            count += 1
            prev = ts
        else:
            periods.append(
                MissingPeriod(
                    start=_as_datetime(start),
                    end=_as_datetime(prev),
                    n_steps=count,
                    series_id=series_id,
                )
            )
            start = ts
            prev = ts
            count = 1
    periods.append(
        MissingPeriod(
            start=_as_datetime(start),
            end=_as_datetime(prev),
            n_steps=count,
            series_id=series_id,
        )
    )
    return periods


def _min_timestamp(stamps: pd.Series) -> datetime | None:
    valid = stamps.dropna()
    if valid.empty:
        return None
    return _as_datetime(valid.min())


def _max_timestamp(stamps: pd.Series) -> datetime | None:
    valid = stamps.dropna()
    if valid.empty:
        return None
    return _as_datetime(valid.max())


def _as_datetime(value: object) -> datetime:
    ts = pd.Timestamp(value)
    if ts.tzinfo is None:
        ts = ts.tz_localize("UTC")
    else:
        ts = ts.tz_convert("UTC")
    return ts.to_pydatetime()
