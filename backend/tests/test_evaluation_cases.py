from __future__ import annotations

import inspect
from pathlib import Path

import numpy as np
import pandas as pd
from evaluation.cases.generators import (
    DATA_DIR,
    REGISTRY_PATH,
    REQUIRED_CASE_IDS,
    generate_case_frame,
    generate_catalog_csvs,
    load_catalog,
)
from evaluation.cases.generators.write_csv import _to_csv_text


def test_registry_contains_the_twelve_required_cases() -> None:
    catalog = load_catalog()
    ids = [case.case_id for case in catalog.cases]
    assert ids[:12] == list(REQUIRED_CASE_IDS)
    assert len(catalog.cases) >= 12
    challenges = {case.expected_challenge for case in catalog.cases}
    assert "trend" in challenges
    assert "seasonality" in challenges
    assert "trend_seasonality" in challenges
    assert "noisy_series" in challenges
    assert "missing_values" in challenges
    assert "outliers" in challenges
    assert "structural_break" in challenges
    assert "contextual_event_change" in challenges
    assert "intermittent_demand" in challenges
    assert "short_history" in challenges
    assert "long_horizon" in challenges
    assert "adversarial_regime_change" in challenges


def test_each_case_has_required_fields_and_time_aware_split() -> None:
    catalog = load_catalog()
    for case in catalog.cases:
        assert case.case_id
        assert case.description
        assert case.frequency
        assert case.history_length >= 1
        assert case.forecast_horizon >= 1
        assert case.expected_challenge
        assert case.generation.kind
        assert isinstance(case.random_seed, int)
        frame = generate_case_frame(case)
        assert len(frame) == case.n_rows
        stamps = pd.DatetimeIndex(frame["timestamp"])
        assert stamps.is_monotonic_increasing
        assert stamps.is_unique
        train_end = stamps[case.train_end_index]
        test_start = stamps[case.history_length]
        assert train_end < test_start
        holdout = case.n_rows - case.history_length
        assert holdout == case.forecast_horizon


def test_generation_twice_is_byte_identical(tmp_path: Path) -> None:
    first = tmp_path / "a"
    second = tmp_path / "b"
    paths_a = generate_catalog_csvs(output_dir=first)
    paths_b = generate_catalog_csvs(output_dir=second)
    assert [path.name for path in paths_a] == [path.name for path in paths_b]
    for left, right in zip(paths_a, paths_b, strict=True):
        assert left.read_bytes() == right.read_bytes()


def test_regeneration_matches_committed_csv_bytes(tmp_path: Path) -> None:
    generated = generate_catalog_csvs(output_dir=tmp_path)
    assert generated
    for path in generated:
        committed = DATA_DIR / path.name
        assert committed.is_file(), f"missing committed CSV {committed}"
        assert path.read_bytes() == committed.read_bytes()


def test_missing_values_only_in_train_and_holdout_finite() -> None:
    case = next(item for item in load_catalog().cases if item.case_id == "005")
    frame = generate_case_frame(case)
    values = frame["value"].to_numpy(dtype=float)
    train = values[: case.history_length]
    holdout = values[case.history_length :]
    assert np.isnan(train).any()
    assert np.isfinite(holdout).all()


def test_event_case_has_context_and_event_columns() -> None:
    case = next(item for item in load_catalog().cases if item.case_id == "008")
    frame = generate_case_frame(case)
    assert "context" in frame.columns
    assert "event" in frame.columns
    assert (frame["event"] == "campaign").sum() == case.generation.event_length


def test_intermittent_has_zeros_and_positive_demand() -> None:
    case = next(item for item in load_catalog().cases if item.case_id == "009")
    frame = generate_case_frame(case)
    values = frame["value"].to_numpy(dtype=float)
    assert (values == 0.0).any()
    assert (values > 0.0).any()


def test_adversarial_regime_changes_after_index() -> None:
    case = next(item for item in load_catalog().cases if item.case_id == "012")
    frame = generate_case_frame(case)
    change = case.generation.regime_change_index
    assert change is not None
    values = frame["value"].to_numpy(dtype=float)
    early = float(np.mean(values[:change]))
    late = float(np.mean(values[change:]))
    assert late > early
    assert case.train_end_index > change
    assert (frame["event"] == "spurious").any()


def test_csv_text_uses_lf_and_zulu_timestamps() -> None:
    case = load_catalog().cases[0]
    text = _to_csv_text(generate_case_frame(case))
    assert "\r" not in text
    assert text.startswith("timestamp,value,series_id\n")
    second = text.split("\n")[1]
    assert "T00:00:00Z" in second


def test_evaluation_package_has_no_fastapi_or_llm() -> None:
    from evaluation.cases import generators
    from evaluation.cases.generators import catalog, synthesize, write_csv

    for module in (generators, catalog, synthesize, write_csv):
        text = inspect.getsource(module).lower()
        assert "import fastapi" not in text
        assert "import openai" not in text
        assert "langgraph" not in text


def test_registry_path_is_the_committed_yaml() -> None:
    assert REGISTRY_PATH.is_file()
    assert REGISTRY_PATH.name == "case_registry.yaml"
