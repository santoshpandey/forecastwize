"""Build synthetic series from a CaseSpec. Isolated RNG per case. No HTTP/LLM."""

from __future__ import annotations

import numpy as np
import pandas as pd

from evaluation.cases.generators.catalog import CaseSpec, GenerationSpec

_VALUE_COL = "value"
_TS_COL = "timestamp"
_ID_COL = "series_id"
_CONTEXT_COL = "context"
_EVENT_COL = "event"


def generate_case_frame(case: CaseSpec) -> pd.DataFrame:
    """Return a new frame: regular timestamps, train then holdout, no shuffle."""
    rng = np.random.default_rng(case.random_seed)
    n = case.n_rows
    spec = case.generation
    timestamps = pd.date_range(
        start=pd.Timestamp(case.start_timestamp),
        periods=n,
        freq=case.frequency,
        tz="UTC",
    )
    values = _values_for_kind(spec, n=n, history_length=case.history_length, rng=rng)
    frame = pd.DataFrame(
        {
            _TS_COL: timestamps,
            _VALUE_COL: values,
            _ID_COL: np.full(n, case.case_id),
        }
    )
    context, event = _optional_labels(spec, n=n)
    if context is not None:
        frame[_CONTEXT_COL] = context
        frame[_EVENT_COL] = event
    return frame


def _values_for_kind(
    spec: GenerationSpec,
    *,
    n: int,
    history_length: int,
    rng: np.random.Generator,
) -> np.ndarray:
    kind = spec.kind
    if kind in {
        "trend",
        "seasonality",
        "trend_seasonality",
        "noisy_trend",
        "short_history",
        "long_horizon",
    }:
        return _trend_season_noise(spec, n=n, rng=rng)
    if kind == "missing_values":
        values = _trend_season_noise(spec, n=n, rng=rng)
        return _apply_missing(values, history_length=history_length, spec=spec, rng=rng)
    if kind == "outliers":
        values = _trend_season_noise(spec, n=n, rng=rng)
        return _apply_outliers(values, history_length=history_length, spec=spec, rng=rng)
    if kind == "structural_break":
        return _structural_break(spec, n=n, rng=rng)
    if kind == "event_context":
        return _event_context(spec, n=n, rng=rng)
    if kind == "intermittent":
        return _intermittent(spec, n=n, rng=rng)
    if kind == "adversarial_regime":
        return _adversarial_regime(spec, n=n, rng=rng)
    msg = f"unsupported generation kind {kind!r}"
    raise ValueError(msg)


def _trend_season_noise(
    spec: GenerationSpec,
    *,
    n: int,
    rng: np.random.Generator,
) -> np.ndarray:
    t = np.arange(n, dtype=np.float64)
    season = _seasonal_component(spec, t)
    noise = rng.normal(0.0, spec.noise_std, size=n)
    return spec.intercept + spec.slope * t + season + noise


def _seasonal_component(spec: GenerationSpec, t: np.ndarray) -> np.ndarray:
    period = spec.seasonal_period
    if period is None or period < 2 or spec.seasonal_amplitude == 0.0:
        return np.zeros(t.size, dtype=np.float64)
    return spec.seasonal_amplitude * np.sin(2.0 * np.pi * t / period)


def _apply_missing(
    values: np.ndarray,
    *,
    history_length: int,
    spec: GenerationSpec,
    rng: np.random.Generator,
) -> np.ndarray:
    fraction = spec.missing_fraction
    if fraction is None or not 0.0 < fraction < 1.0:
        msg = "missing_values requires missing_fraction in (0, 1)"
        raise ValueError(msg)
    out = values.copy()
    n_missing = max(1, int(np.floor(fraction * history_length)))
    n_missing = min(n_missing, history_length)
    indices = rng.choice(history_length, size=n_missing, replace=False)
    out[np.sort(indices)] = np.nan
    return out


def _apply_outliers(
    values: np.ndarray,
    *,
    history_length: int,
    spec: GenerationSpec,
    rng: np.random.Generator,
) -> np.ndarray:
    if spec.n_outliers is None or spec.n_outliers < 1:
        msg = "outliers requires n_outliers >= 1"
        raise ValueError(msg)
    if spec.outlier_magnitude is None:
        msg = "outliers requires outlier_magnitude"
        raise ValueError(msg)
    out = values.copy()
    count = min(spec.n_outliers, history_length)
    indices = rng.choice(history_length, size=count, replace=False)
    signs = rng.choice(np.array([-1.0, 1.0]), size=count)
    out[indices] = out[indices] + signs * spec.outlier_magnitude
    return out


def _structural_break(
    spec: GenerationSpec,
    *,
    n: int,
    rng: np.random.Generator,
) -> np.ndarray:
    if spec.break_index is None or spec.break_shift is None:
        msg = "structural_break requires break_index and break_shift"
        raise ValueError(msg)
    if not 0 < spec.break_index < n:
        msg = "break_index must be inside the generated series"
        raise ValueError(msg)
    values = _trend_season_noise(spec, n=n, rng=rng)
    values[spec.break_index :] = values[spec.break_index :] + spec.break_shift
    return values


def _event_context(
    spec: GenerationSpec,
    *,
    n: int,
    rng: np.random.Generator,
) -> np.ndarray:
    if spec.event_start_index is None or spec.event_length is None or spec.event_shift is None:
        msg = "event_context requires event_start_index, event_length, and event_shift"
        raise ValueError(msg)
    values = _trend_season_noise(spec, n=n, rng=rng)
    start = spec.event_start_index
    end = min(n, start + spec.event_length)
    values[start:end] = values[start:end] + spec.event_shift
    return values


def _intermittent(
    spec: GenerationSpec,
    *,
    n: int,
    rng: np.random.Generator,
) -> np.ndarray:
    if spec.occurrence_probability is None or spec.demand_low is None or spec.demand_high is None:
        msg = "intermittent requires occurrence_probability, demand_low, and demand_high"
        raise ValueError(msg)
    if not 0.0 < spec.occurrence_probability < 1.0:
        msg = "occurrence_probability must be in (0, 1)"
        raise ValueError(msg)
    if spec.demand_high < spec.demand_low:
        msg = "demand_high must be >= demand_low"
        raise ValueError(msg)
    occurs = rng.random(n) < spec.occurrence_probability
    demand = rng.integers(spec.demand_low, spec.demand_high + 1, size=n).astype(np.float64)
    return np.where(occurs, demand, 0.0)


def _adversarial_regime(
    spec: GenerationSpec,
    *,
    n: int,
    rng: np.random.Generator,
) -> np.ndarray:
    if (
        spec.regime_change_index is None
        or spec.regime_level_shift is None
        or spec.regime_seasonal_sign is None
        or spec.regime_noise_std is None
    ):
        msg = (
            "adversarial_regime requires regime_change_index, regime_level_shift, "
            "regime_seasonal_sign, and regime_noise_std"
        )
        raise ValueError(msg)
    change = spec.regime_change_index
    if not 0 < change < n:
        msg = "regime_change_index must be inside the generated series"
        raise ValueError(msg)
    t = np.arange(n, dtype=np.float64)
    season = _seasonal_component(spec, t)
    noise_a = rng.normal(0.0, spec.noise_std, size=n)
    noise_b = rng.normal(0.0, spec.regime_noise_std, size=n)
    early = spec.intercept + spec.slope * t + season + noise_a
    late = (
        spec.intercept
        + spec.regime_level_shift
        + spec.slope * t
        + spec.regime_seasonal_sign * season
        + noise_b
    )
    values = early.copy()
    values[change:] = late[change:]
    return values


def _optional_labels(
    spec: GenerationSpec,
    *,
    n: int,
) -> tuple[np.ndarray | None, np.ndarray | None]:
    if spec.kind == "event_context":
        if spec.event_start_index is None or spec.event_length is None:
            msg = "event_context labels require event_start_index and event_length"
            raise ValueError(msg)
        context = np.full(n, "", dtype=object)
        event = np.full(n, "", dtype=object)
        start = spec.event_start_index
        end = min(n, start + spec.event_length)
        context[start:end] = "promo"
        event[start:end] = "campaign"
        return context, event
    if spec.kind == "adversarial_regime":
        context = np.full(n, "", dtype=object)
        event = np.full(n, "", dtype=object)
        end = spec.spurious_event_end_index
        if end is None:
            end = 0
        end = min(n, max(0, end))
        context[:end] = "stable_looks_fine"
        event[:end] = "spurious"
        return context, event
    return None, None
