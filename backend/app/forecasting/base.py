"""Common forecast model interface and typed result. No HTTP adapter, LLM, or concrete models."""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import UTC, datetime
from typing import Self

import numpy as np
import pandas as pd
from pydantic import BaseModel, ConfigDict, Field, field_serializer, model_validator

ConfigValue = str | int | float | bool | None


def _to_utc_iso(value: datetime) -> str:
    aware = value if value.tzinfo is not None else value.replace(tzinfo=UTC)
    return aware.astimezone(UTC).isoformat().replace("+00:00", "Z")


class ModelNotFittedError(RuntimeError):
    """Raised when predict/predict_interval/metadata need a prior successful fit."""


class ForecastInterfaceError(ValueError):
    """Invalid horizon, frequency, or array shapes at the model boundary."""


class TrainingRange(BaseModel):
    model_config = ConfigDict(extra="forbid")

    start: datetime
    end: datetime

    @field_serializer("start", "end")
    def serialize_bounds(self, value: datetime) -> str:
        return _to_utc_iso(value)

    @model_validator(mode="after")
    def start_not_after_end(self) -> TrainingRange:
        if self.start > self.end:
            msg = "training_range.start must be <= training_range.end"
            raise ValueError(msg)
        return self


class ModelMetadata(BaseModel):
    """Identity returned by ForecastModel.metadata() after fit."""

    model_config = ConfigDict(extra="forbid")

    model: str
    training_range: TrainingRange
    frequency: str
    configuration: dict[str, ConfigValue]
    random_seed: int | None = None
    n_train: int


class ForecastResult(BaseModel):
    """Canonical forecast artifact. Numerical fields come from deterministic models only."""

    model_config = ConfigDict(extra="forbid")

    timestamps: list[datetime]
    yhat: list[float] = Field(description="Point forecasts")
    lower: list[float] = Field(description="Lower prediction interval")
    upper: list[float] = Field(description="Upper prediction interval")
    model: str
    training_range: TrainingRange
    forecast_horizon: int
    frequency: str
    configuration: dict[str, ConfigValue]
    random_seed: int | None = None
    generated_at: datetime
    interval_coverage_nominal: float = Field(
        description="Nominal coverage of lower/upper (e.g. 0.95), not empirical coverage."
    )

    @field_serializer("timestamps")
    def serialize_timestamps(self, value: list[datetime]) -> list[str]:
        return [_to_utc_iso(item) for item in value]

    @field_serializer("generated_at")
    def serialize_generated_at(self, value: datetime) -> str:
        return _to_utc_iso(value)

    @model_validator(mode="after")
    def aligned_horizon_and_intervals(self) -> ForecastResult:
        n = self.forecast_horizon
        if n < 1:
            msg = "forecast_horizon must be >= 1"
            raise ValueError(msg)
        if not (0.0 < self.interval_coverage_nominal < 1.0):
            msg = "interval_coverage_nominal must be in (0, 1)"
            raise ValueError(msg)
        if self.frequency.strip() == "":
            msg = "frequency must be a non-empty explicit alias"
            raise ValueError(msg)
        lengths = {
            "timestamps": len(self.timestamps),
            "yhat": len(self.yhat),
            "lower": len(self.lower),
            "upper": len(self.upper),
        }
        if any(length != n for length in lengths.values()):
            msg = (
                "timestamps/yhat/lower/upper must each have length "
                f"forecast_horizon={n}; got {lengths}"
            )
            raise ValueError(msg)
        for i, (lo, hi) in enumerate(zip(self.lower, self.upper, strict=True)):
            if np.isfinite(lo) and np.isfinite(hi) and lo > hi:
                msg = f"lower[{i}] > upper[{i}]; interval ordering is invalid"
                raise ValueError(msg)
        return self


class ForecastModel(ABC):
    """Shared interface for baseline and candidate models.

    Implementations must copy training inputs (never mutate caller arrays) and must
    not import HTTP adapters, HTTP clients, or LLMs. Model *selection* is not part of this
    class; callers choose a strategy_id from backtest evidence, then fit/predict.
    """

    @abstractmethod
    def fit(
        self,
        timestamps: pd.Series | pd.DatetimeIndex,
        values: pd.Series | np.ndarray,
        *,
        frequency: str,
        seed: int | None = None,
    ) -> Self:
        """Train on data ending at the last training timestamp. Return self."""

    @abstractmethod
    def predict(self, *, horizon: int) -> np.ndarray:
        """Point forecasts of length `horizon`. Horizon is explicit (not inferred)."""

    @abstractmethod
    def predict_interval(
        self,
        *,
        horizon: int,
        coverage: float = 0.95,
    ) -> tuple[np.ndarray, np.ndarray]:
        """Lower and upper arrays of length `horizon` for the given nominal coverage."""

    @abstractmethod
    def metadata(self) -> ModelMetadata:
        """Model identity, training range, frequency, config, and seed after fit."""

    def minimum_train_size(self, *, frequency: str) -> int:
        """Smallest training length for which ``fit`` is allowed.

        Concrete models override this with the same rules ``fit`` enforces.
        Default is 1 (non-empty series). Does not inspect holdout or emit yhat.
        ``frequency`` is part of the contract because seasonal models resolve
        period from frequency when the constructor did not fix it.
        """
        if not frequency or not str(frequency).strip():
            msg = "frequency must be a non-empty explicit alias"
            raise ForecastInterfaceError(msg)
        return 1


def assemble_forecast_result(
    *,
    timestamps: pd.Series | pd.DatetimeIndex | list[datetime],
    yhat: np.ndarray | list[float],
    lower: np.ndarray | list[float],
    upper: np.ndarray | list[float],
    metadata: ModelMetadata,
    forecast_horizon: int,
    interval_coverage_nominal: float,
    generated_at: datetime | None = None,
) -> ForecastResult:
    """Build a ForecastResult from model outputs. Does not fit or select a model."""
    stamp_list = _as_datetime_list(timestamps)
    created = generated_at if generated_at is not None else datetime.now(UTC)
    return ForecastResult(
        timestamps=stamp_list,
        yhat=_as_float_list(yhat),
        lower=_as_float_list(lower),
        upper=_as_float_list(upper),
        model=metadata.model,
        training_range=metadata.training_range,
        forecast_horizon=forecast_horizon,
        frequency=metadata.frequency,
        configuration=dict(metadata.configuration),
        random_seed=metadata.random_seed,
        generated_at=created,
        interval_coverage_nominal=interval_coverage_nominal,
    )


def _as_float_list(values: np.ndarray | list[float]) -> list[float]:
    arr = np.asarray(values, dtype=float)
    return [float(item) for item in arr.tolist()]


def _as_datetime_list(
    timestamps: pd.Series | pd.DatetimeIndex | list[datetime],
) -> list[datetime]:
    if isinstance(timestamps, list):
        return list(timestamps)
    index = pd.DatetimeIndex(timestamps)
    out: list[datetime] = []
    for ts in index:
        aware = pd.Timestamp(ts)
        if aware.tzinfo is None:
            aware = aware.tz_localize("UTC")
        else:
            aware = aware.tz_convert("UTC")
        converted = aware.to_pydatetime()
        if converted.tzinfo is None:
            out.append(converted.replace(tzinfo=UTC))
        else:
            out.append(converted.astimezone(UTC))
    return out
