"""Load and validate the shared evaluation case registry. No FastAPI or LLM."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

REPO_ROOT = Path(__file__).resolve().parents[3]
REGISTRY_PATH = Path(__file__).resolve().parents[1] / "case_registry.yaml"
DATA_DIR = REPO_ROOT / "data" / "evaluation"

REQUIRED_CASE_IDS = (
    "001",
    "002",
    "003",
    "004",
    "005",
    "006",
    "007",
    "008",
    "009",
    "010",
    "011",
    "012",
)

GenerationKind = Literal[
    "trend",
    "seasonality",
    "trend_seasonality",
    "noisy_trend",
    "missing_values",
    "outliers",
    "structural_break",
    "event_context",
    "intermittent",
    "short_history",
    "long_horizon",
    "adversarial_regime",
]


class GenerationSpec(BaseModel):
    """Kind-specific parameters. Extra fields are rejected so YAML stays explicit."""

    model_config = ConfigDict(extra="forbid")

    kind: GenerationKind
    intercept: float = 0.0
    slope: float = 0.0
    noise_std: float = 0.0
    seasonal_period: int | None = None
    seasonal_amplitude: float = 0.0
    missing_fraction: float | None = None
    n_outliers: int | None = None
    outlier_magnitude: float | None = None
    break_index: int | None = None
    break_shift: float | None = None
    event_start_index: int | None = None
    event_length: int | None = None
    event_shift: float | None = None
    occurrence_probability: float | None = None
    demand_low: int | None = None
    demand_high: int | None = None
    regime_change_index: int | None = None
    regime_level_shift: float | None = None
    regime_seasonal_sign: float | None = None
    regime_noise_std: float | None = None
    spurious_event_end_index: int | None = None


class CaseSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    case_id: str
    name: str
    description: str
    frequency: str
    history_length: int
    forecast_horizon: int
    expected_challenge: str
    random_seed: int
    start_timestamp: str
    csv_filename: str
    generation: GenerationSpec

    @model_validator(mode="after")
    def lengths_and_split(self) -> CaseSpec:
        if self.history_length < 1:
            msg = "history_length must be >= 1"
            raise ValueError(msg)
        if self.forecast_horizon < 1:
            msg = "forecast_horizon must be >= 1"
            raise ValueError(msg)
        if not self.frequency.strip():
            msg = "frequency must be a non-empty explicit alias"
            raise ValueError(msg)
        if not self.csv_filename.endswith(".csv"):
            msg = "csv_filename must end with .csv"
            raise ValueError(msg)
        return self

    @property
    def n_rows(self) -> int:
        return self.history_length + self.forecast_horizon

    @property
    def train_end_index(self) -> int:
        """Inclusive last training index. Holdout starts at train_end_index + 1."""
        return self.history_length - 1


class EvaluationCatalog(BaseModel):
    model_config = ConfigDict(extra="forbid")

    catalog_id: str
    catalog_version: int
    notes: str
    cases: list[CaseSpec] = Field(min_length=12)

    @model_validator(mode="after")
    def unique_ids_and_required_set(self) -> EvaluationCatalog:
        ids = [case.case_id for case in self.cases]
        if len(ids) != len(set(ids)):
            msg = "case_id values must be unique"
            raise ValueError(msg)
        missing = [case_id for case_id in REQUIRED_CASE_IDS if case_id not in ids]
        if missing:
            msg = f"catalog missing required case_id(s): {missing}"
            raise ValueError(msg)
        names = [case.csv_filename for case in self.cases]
        if len(names) != len(set(names)):
            msg = "csv_filename values must be unique"
            raise ValueError(msg)
        return self


def load_catalog(path: Path | None = None) -> EvaluationCatalog:
    registry = path if path is not None else REGISTRY_PATH
    payload = yaml.safe_load(registry.read_text(encoding="utf-8"))
    return EvaluationCatalog.model_validate(payload)
