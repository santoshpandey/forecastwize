from __future__ import annotations

import inspect
import subprocess
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pytest
from app.forecasting.base import ForecastInterfaceError
from app.services import forecast_service as forecast_service_module
from app.services.forecast_service import (
    BASELINE_MODEL_IDS,
    create_baseline_model,
    run_baseline_forecast,
)
from evaluation.cases.generators import load_catalog

from tests.ts_fixtures import daily_index, trend_seasonal


def test_forecast_service_source_has_no_fastapi_or_llm() -> None:
    text = inspect.getsource(forecast_service_module).lower()
    assert "import fastapi" not in text
    assert "import openai" not in text
    assert "langgraph" not in text


def test_create_baseline_model_requires_explicit_id() -> None:
    with pytest.raises(TypeError):
        create_baseline_model()  # type: ignore[call-arg]
    with pytest.raises(ForecastInterfaceError, match="Unknown baseline"):
        create_baseline_model("best")
    naive = create_baseline_model("naive")
    assert naive.__class__.__name__ == "NaiveModel"
    assert BASELINE_MODEL_IDS == ("naive", "seasonal_naive", "ets", "arima")


def test_run_baseline_forecast_requires_model_id_and_is_deterministic() -> None:
    stamps = daily_index(14)
    values = trend_seasonal(14)
    generated = datetime(2021, 6, 1, tzinfo=UTC)
    first = run_baseline_forecast(
        stamps,
        values,
        frequency="D",
        horizon=3,
        model_id="naive",
        coverage=0.9,
        seed=1,
        generated_at=generated,
    )
    second = run_baseline_forecast(
        stamps,
        values,
        frequency="D",
        horizon=3,
        model_id="naive",
        coverage=0.9,
        seed=1,
        generated_at=generated,
    )
    assert first.model == "naive"
    assert first.forecast_horizon == 3
    assert first.frequency == "D"
    assert first.interval_coverage_nominal == 0.9
    assert first.random_seed == 1
    assert first.generated_at == generated
    assert first.yhat == second.yhat
    assert first.lower == second.lower
    assert first.upper == second.upper
    assert len(first.timestamps) == 3
    assert all(lo <= hi for lo, hi in zip(first.lower, first.upper, strict=True))
    with pytest.raises(TypeError):
        run_baseline_forecast(  # type: ignore[call-arg]
            stamps, values, frequency="D", horizon=3
        )


def test_run_baseline_seasonal_naive_explicitly() -> None:
    stamps = daily_index(14)
    values = np.arange(14, dtype=float)
    result = run_baseline_forecast(
        stamps,
        values,
        frequency="D",
        horizon=7,
        model_id="seasonal_naive",
        generated_at=datetime(2021, 1, 1, tzinfo=UTC),
    )
    assert result.model == "seasonal_naive"
    np.testing.assert_allclose(result.yhat, values[-7:].tolist())


def test_no_evaluation_run_artifacts() -> None:
    """Scratch eval copies are gitignored. Named experiment pairs may be tracked."""
    repo = Path(__file__).resolve().parents[2]
    tracked = subprocess.check_output(
        ["git", "ls-files", "evaluation/artifacts"],
        cwd=repo,
        text=True,
    )
    allowed_prefixes = (
        "evaluation/artifacts/.gitkeep",
        "evaluation/artifacts/exp-initial-comparison/",
        "evaluation/artifacts/EXP-",
        "evaluation/artifacts/pre-exp010-promotion/",
    )
    leftover = [
        line.strip()
        for line in tracked.splitlines()
        if line.strip() and not line.strip().startswith(allowed_prefixes)
    ]
    assert leftover == []
    data_eval = repo / "data" / "evaluation"
    allowed_names = {"README.md"}
    catalog = load_catalog()
    allowed_names.update(case.csv_filename for case in catalog.cases)
    unexpected = [
        path.name
        for path in data_eval.iterdir()
        if path.is_file() and path.name not in allowed_names
    ]
    assert unexpected == []
