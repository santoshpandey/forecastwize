from __future__ import annotations

import inspect
import json
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from app.agents.data_detective import run_data_detective
from app.agents.state import DATA_DETECTIVE_AGENT_ID, DATA_DETECTIVE_MAX_RETRIES
from app.forecasting.base import ForecastInterfaceError
from app.tools.data_tools import reject_unknown_data_tool

from tests.ts_fixtures import daily_index, trend_seasonal

_TRAJECTORY_RECORD = (
    Path(__file__).resolve().parents[2] / "trajectories" / "data_detective_test.jsonl"
)


def _required_trajectory_fields() -> tuple[str, ...]:
    return (
        "run_id",
        "agent_id",
        "timestamp",
        "input_state",
        "tool_requested",
        "tool_result",
        "decision",
        "evidence_ids",
        "retry_number",
        "final_status",
    )


def test_data_detective_source_does_not_forecast_or_call_llm() -> None:
    from app.agents import data_detective
    from app.agents import state as state_mod

    for module in (data_detective, state_mod):
        text = inspect.getsource(module).lower()
        assert "import fastapi" not in text
        assert "import openai" not in text
        assert "langgraph" not in text
        assert "run_baseline_forecast" not in text
        assert "wis(" not in text


def test_retry_limit_is_finite() -> None:
    assert DATA_DETECTIVE_MAX_RETRIES >= 0
    assert DATA_DETECTIVE_MAX_RETRIES <= 3


def test_unknown_tool_still_rejected_from_agent_layer() -> None:
    with pytest.raises(ForecastInterfaceError, match="Unknown tool"):
        reject_unknown_data_tool("invent_events")


def test_normal_series(tmp_path: Path) -> None:
    n = 56
    stamps = daily_index(n)
    t = np.arange(n, dtype=float)
    values = 10.0 + 0.02 * t + 3.0 * np.sin(2.0 * np.pi * t / 7.0)
    original = values.copy()
    traj = tmp_path / "normal.jsonl"
    state = run_data_detective(
        stamps,
        values,
        frequency="D",
        seasonal_period=7,
        run_id="test-normal",
        generated_at=datetime(2021, 1, 1, tzinfo=UTC),
        trajectory_path=traj,
    )
    np.testing.assert_array_equal(values, original)
    assert state.status == "completed"
    assert state.report is not None
    report = state.report
    assert report.emitted_forecast is False
    assert report.modified_dataset is False
    assert "yhat" not in report.model_dump()
    dump = json.dumps(report.model_dump(mode="json")).lower()
    assert "yhat" not in dump
    assert "promo" not in dump
    assert "holiday" not in dump
    for claim in (*report.claims, *report.risks):
        assert claim.evidence_ids
        for eid in claim.evidence_ids:
            assert eid in state.evidence
    season_obs = [c for c in report.claims if c.topic == "seasonality" and c.kind == "observation"]
    assert season_obs
    season_eid = season_obs[0].evidence_ids[0]
    assert state.evidence[season_eid].payload.get("detected") is True
    no_event = [c for c in report.claims if "no event column" in c.statement.lower()]
    assert no_event
    assert traj.is_file()
    lines = [json.loads(line) for line in traj.read_text(encoding="utf-8").splitlines() if line]
    assert lines
    assert lines[-1]["final_status"] == "completed"
    assert lines[-1]["agent_id"] == DATA_DETECTIVE_AGENT_ID
    for row in lines:
        for field in _required_trajectory_fields():
            assert field in row
    assert any(row["tool_requested"] == "inspect_series" for row in lines)
    assert any(row["tool_requested"] is None and row["decision"] for row in lines)


def test_anomalous_series(tmp_path: Path) -> None:
    rng = np.random.default_rng(0)
    values = rng.normal(0.0, 1.0, 40)
    values[10] = 25.0
    original = values.copy()
    state = run_data_detective(
        daily_index(40),
        values,
        frequency="D",
        run_id="test-anomaly",
        generated_at=datetime(2021, 1, 2, tzinfo=UTC),
        trajectory_path=tmp_path / "anom.jsonl",
    )
    np.testing.assert_array_equal(values, original)
    assert state.status == "completed"
    assert state.report is not None
    anomaly_obs = [
        c for c in state.report.claims if c.topic == "anomalies" and c.kind == "observation"
    ]
    assert anomaly_obs
    detected_any = False
    for claim in anomaly_obs:
        for eid in claim.evidence_ids:
            if state.evidence[eid].payload.get("detected") is True:
                detected_any = True
    assert detected_any
    assert any(r.topic == "anomalies" for r in state.report.risks)
    assert state.report.forecastability in {"limited", "adequate", "poor"}
    assert "clip" in " ".join(i.action.lower() for i in state.report.investigations)


def test_missing_values_propose_transform_without_mutating(tmp_path: Path) -> None:
    values = np.array([1.0, 2.0, np.nan, 4.0, 5.0, 6.0, 7.0, 8.0], dtype=float)
    original = values.copy()
    state = run_data_detective(
        daily_index(8),
        values,
        frequency="D",
        run_id="test-missing",
        generated_at=datetime(2021, 1, 4, tzinfo=UTC),
        trajectory_path=tmp_path / "missing.jsonl",
    )
    np.testing.assert_array_equal(values, original)
    assert state.report is not None
    assert state.report.modified_dataset is False
    names = [item.name for item in state.report.proposed_transforms]
    assert "missing_value_policy" in names
    assert all(item.applied is False for item in state.report.proposed_transforms)


def test_structural_break(tmp_path: Path) -> None:
    values = np.concatenate([np.full(40, 0.0), np.full(40, 8.0)])
    original = values.copy()
    state = run_data_detective(
        daily_index(80),
        values,
        frequency="D",
        run_id="test-break",
        generated_at=datetime(2021, 1, 3, tzinfo=UTC),
        trajectory_path=tmp_path / "break.jsonl",
    )
    np.testing.assert_array_equal(values, original)
    assert state.status == "completed"
    assert state.report is not None
    break_obs = [
        c
        for c in (*state.report.claims, *state.report.risks)
        if c.topic == "structural_change" and c.kind == "observation"
    ]
    assert break_obs
    eid = break_obs[0].evidence_ids[0]
    assert state.evidence[eid].payload.get("detected") is True
    hyps = [c for c in state.report.claims + state.report.risks if c.kind == "hypothesis"]
    assert hyps
    assert all(h.evidence_ids for h in hyps)
    assert state.report.forecastability == "limited"
    assert state.report.overall_uncertainty == "high"


def test_insufficient_history(tmp_path: Path) -> None:
    values = np.array([1.0, 2.0, 2.2, 1.8, 2.1], dtype=float)
    state = run_data_detective(
        daily_index(5),
        values,
        frequency="D",
        run_id="test-short",
        generated_at=datetime(2021, 1, 4, tzinfo=UTC),
        trajectory_path=tmp_path / "short.jsonl",
    )
    assert state.status == "completed"
    assert state.report is not None
    assert state.report.forecastability in {"poor", "limited"}
    assert state.report.overall_uncertainty == "high"
    trend_obs = [c for c in state.report.claims if c.topic == "trend" and c.kind == "observation"]
    assert trend_obs
    trend_eid = trend_obs[0].evidence_ids[0]
    assert state.evidence[trend_eid].payload.get("detected") is False
    text = " ".join(c.statement.lower() for c in trend_obs)
    assert "insufficient" in text or "did not make a positive detection" in text
    assert any(
        "history" in i.action.lower() or "period" in i.action.lower()
        for i in state.report.investigations
    )


def test_invalid_input_length_mismatch(tmp_path: Path) -> None:
    state = run_data_detective(
        daily_index(3),
        np.arange(8, dtype=float),
        frequency="D",
        run_id="test-invalid",
        generated_at=datetime(2021, 1, 5, tzinfo=UTC),
        trajectory_path=tmp_path / "invalid.jsonl",
    )
    assert state.status == "failed"
    assert state.report is not None
    assert state.report.forecastability == "unknown"
    assert state.report.emitted_forecast is False
    assert any(c.topic == "input" for c in state.report.claims)
    assert (
        "length" in (state.error_message or "").lower()
        or "length" in state.report.claims[0].statement.lower()
    )
    screens = [item.tool_name for item in state.evidence.values()]
    assert "diagnose_trend" not in screens
    lines = [
        json.loads(line)
        for line in (tmp_path / "invalid.jsonl").read_text(encoding="utf-8").splitlines()
        if line
    ]
    assert any(row["final_status"] == "failed" for row in lines)


def test_invalid_input_empty_and_unparseable(tmp_path: Path) -> None:
    empty = run_data_detective(
        daily_index(0),
        np.array([], dtype=float),
        run_id="test-empty",
        generated_at=datetime(2021, 1, 6, tzinfo=UTC),
        trajectory_path=tmp_path / "empty.jsonl",
    )
    assert empty.status == "failed"
    bad_ts = run_data_detective(
        pd.Series(["not-a-date"] * 8),
        np.arange(8, dtype=float),
        run_id="test-bad-ts",
        generated_at=datetime(2021, 1, 7, tzinfo=UTC),
        trajectory_path=tmp_path / "badts.jsonl",
    )
    assert bad_ts.status == "failed"
    assert bad_ts.report is not None
    assert all(c.evidence_ids for c in bad_ts.report.claims)


def test_records_trajectory_for_test_execution() -> None:
    n = 56
    values = trend_seasonal(n)
    _TRAJECTORY_RECORD.parent.mkdir(parents=True, exist_ok=True)
    state = run_data_detective(
        daily_index(n),
        values,
        frequency="D",
        seasonal_period=7,
        run_id="data-detective-pytest",
        generated_at=datetime(2021, 6, 1, tzinfo=UTC),
        trajectory_path=_TRAJECTORY_RECORD,
    )
    assert _TRAJECTORY_RECORD.is_file()
    rows = [
        json.loads(line)
        for line in _TRAJECTORY_RECORD.read_text(encoding="utf-8").splitlines()
        if line
    ]
    assert len(rows) == len(state.trajectory)
    assert rows[-1]["run_id"] == "data-detective-pytest"
    assert rows[-1]["final_status"] in {"completed", "failed"}
    for row in rows:
        for field in _required_trajectory_fields():
            assert field in row
        assert row["retry_number"] <= DATA_DETECTIVE_MAX_RETRIES
    # Append-only within the run: prior tool steps remain.
    tools = [row["tool_requested"] for row in rows if row["tool_requested"]]
    assert tools[0] == "inspect_series"
    assert len(tools) >= 2
