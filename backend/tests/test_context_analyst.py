from __future__ import annotations

import inspect
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from app.agents.context_analyst import (
    ContextDiagnosticsHint,
    ContextFinding,
    run_context_analyst,
)
from app.agents.state import CONTEXT_ANALYST_AGENT_ID, CONTEXT_ANALYST_MAX_RETRIES
from app.forecasting.base import ForecastInterfaceError
from app.tools.context_tools import (
    ContextualRecord,
    classify_event_label,
    reject_unknown_context_tool,
    run_inspect_context_tool,
)

from tests.ts_fixtures import daily_index

_TRAJECTORY_FIELDS = (
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


def test_context_analyst_source_does_not_forecast_or_call_llm() -> None:
    from app.agents import context_analyst

    text = inspect.getsource(context_analyst).lower()
    assert "import fastapi" not in text
    assert "import openai" not in text
    assert "langgraph" not in text
    assert "run_baseline_forecast" not in text
    assert "yhat =" not in text
    sig = inspect.signature(run_context_analyst)
    assert "values" not in sig.parameters
    assert "yhat" not in sig.parameters


def test_retry_limit_is_finite() -> None:
    assert CONTEXT_ANALYST_MAX_RETRIES >= 0
    assert CONTEXT_ANALYST_MAX_RETRIES <= 3


def test_unknown_tool_rejected() -> None:
    with pytest.raises(ForecastInterfaceError, match="Unknown tool"):
        reject_unknown_context_tool("invent_events")


def test_classify_known_event_kinds() -> None:
    assert classify_event_label("promotion") == "promotion"
    assert classify_event_label("promo") == "promotion"
    assert classify_event_label("holiday") == "holiday"
    assert classify_event_label("campaign") == "campaign"
    assert classify_event_label("price change") == "price_change"
    assert classify_event_label("stockout") == "stockout"
    assert classify_event_label("product launch") == "product_launch"
    assert classify_event_label("external business event") == "external_business_event"
    assert classify_event_label("spurious") == "unrecognized"


def test_no_context_states_analysis_unavailable(tmp_path: Path) -> None:
    state = run_context_analyst(
        timestamps=daily_index(10),
        run_id="test-no-context",
        generated_at=datetime(2021, 1, 1, tzinfo=UTC),
        trajectory_path=tmp_path / "none.jsonl",
    )
    assert state.status == "completed"
    assert state.report is not None
    report = state.report
    assert report.context_available is False
    assert report.unavailable_reason is not None
    assert "unavailable" in report.unavailable_reason.lower()
    assert report.possible_explanations == []
    assert report.emitted_forecast is False
    assert report.forecast_adjusted is False
    assert "yhat" not in report.model_dump()
    facts = " ".join(item.statement.lower() for item in report.observed_facts)
    assert "contextual analysis is unavailable" in facts


def test_notes_are_not_parsed_into_events(tmp_path: Path) -> None:
    state = run_context_analyst(
        notes="There was a holiday promotion that caused a spike.",
        run_id="test-notes",
        generated_at=datetime(2021, 1, 2, tzinfo=UTC),
        trajectory_path=tmp_path / "notes.jsonl",
    )
    report = state.report
    assert report is not None
    assert report.context_available is False
    dump = json.dumps(report.model_dump(mode="json")).lower()
    observed = " ".join(item.statement.lower() for item in report.observed_facts)
    assert "holiday" not in observed or "not treated as observed events" in observed
    assert not any(item.event_kind == "holiday" for item in report.observed_facts)
    assert "caused" not in dump


def test_labeled_events_are_observed_facts_not_causes(tmp_path: Path) -> None:
    n = 14
    stamps = daily_index(n)
    events = [""] * n
    context = [""] * n
    for i in range(3, 6):
        events[i] = "campaign"
        context[i] = "promo"
    original_events = list(events)
    state = run_context_analyst(
        timestamps=stamps,
        event_labels=events,
        context_labels=context,
        run_id="test-campaign",
        generated_at=datetime(2021, 1, 3, tzinfo=UTC),
        trajectory_path=tmp_path / "campaign.jsonl",
    )
    assert events == original_events
    assert state.status == "completed"
    report = state.report
    assert report is not None
    assert report.context_available is True
    assert report.forecast_adjusted is False
    assert "campaign" in report.recognized_event_kinds
    assert "promotion" in report.recognized_event_kinds
    facts = [item for item in report.observed_facts if item.event_kind == "campaign"]
    assert facts
    assert all(item.kind == "observed_fact" for item in report.observed_facts)
    assert all(item.kind == "possible_explanation" for item in report.possible_explanations)
    assert report.possible_explanations
    assert "possible explanation" in report.possible_explanations[0].statement.lower()
    dump = json.dumps(report.model_dump(mode="json")).lower()
    assert "caused" not in dump
    assert "yhat" not in dump
    for item in (*report.observed_facts, *report.possible_explanations):
        assert item.asserts_causality is False
        assert item.evidence_ids
        for eid in item.evidence_ids:
            assert eid in state.evidence
    lines = [
        json.loads(line)
        for line in (tmp_path / "campaign.jsonl").read_text(encoding="utf-8").splitlines()
        if line
    ]
    assert lines[-1]["final_status"] == "completed"
    assert lines[-1]["agent_id"] == CONTEXT_ANALYST_AGENT_ID
    for row in lines:
        for field in _TRAJECTORY_FIELDS:
            assert field in row
    assert any(row["tool_requested"] == "inspect_context" for row in lines)


def test_all_supported_event_kinds_are_recognized(tmp_path: Path) -> None:
    labels = [
        "promotion",
        "holiday",
        "campaign",
        "price change",
        "stockout",
        "product launch",
        "external business event",
    ]
    stamps = daily_index(len(labels))
    state = run_context_analyst(
        timestamps=stamps,
        event_labels=labels,
        run_id="test-kinds",
        generated_at=datetime(2021, 1, 4, tzinfo=UTC),
        trajectory_path=tmp_path / "kinds.jsonl",
    )
    report = state.report
    assert report is not None
    expected = {
        "promotion",
        "holiday",
        "campaign",
        "price_change",
        "stockout",
        "product_launch",
        "external_business_event",
    }
    assert set(report.recognized_event_kinds) == expected


def test_unrecognized_label_is_not_invented_as_known_kind(tmp_path: Path) -> None:
    stamps = daily_index(4)
    state = run_context_analyst(
        timestamps=stamps,
        event_labels=["", "spurious", "", ""],
        run_id="test-unrecognized",
        generated_at=datetime(2021, 1, 5, tzinfo=UTC),
        trajectory_path=tmp_path / "unrec.jsonl",
    )
    report = state.report
    assert report is not None
    kinds = [item.event_kind for item in report.observed_facts if item.event_kind is not None]
    assert "unrecognized" in kinds
    assert "campaign" not in report.recognized_event_kinds


def test_diagnostics_hint_stays_a_possible_explanation(tmp_path: Path) -> None:
    n = 8
    stamps = daily_index(n)
    events = [""] * n
    events[2] = "stockout"
    events[3] = "stockout"
    hint = ContextDiagnosticsHint(
        anomalies_detected=True,
        anomaly_timestamps=[stamps[2].to_pydatetime()],
    )
    state = run_context_analyst(
        timestamps=stamps,
        event_labels=events,
        diagnostics_hint=hint,
        run_id="test-hint",
        generated_at=datetime(2021, 1, 6, tzinfo=UTC),
        trajectory_path=tmp_path / "hint.jsonl",
    )
    report = state.report
    assert report is not None
    expl = report.possible_explanations[0].statement.lower()
    assert "possible explanation" in expl
    assert "not a causal" in expl
    assert "caused" not in expl


def test_structured_records_are_optional_context(tmp_path: Path) -> None:
    rec = ContextualRecord(
        start=datetime(2020, 1, 10, tzinfo=UTC),
        end=datetime(2020, 1, 12, tzinfo=UTC),
        event_label="holiday",
    )
    state = run_context_analyst(
        records=[rec],
        run_id="test-record",
        generated_at=datetime(2021, 1, 7, tzinfo=UTC),
        trajectory_path=tmp_path / "record.jsonl",
    )
    report = state.report
    assert report is not None
    assert report.context_available is True
    assert "holiday" in report.recognized_event_kinds


def test_length_mismatch_fails_and_does_not_invent_alignment(tmp_path: Path) -> None:
    state = run_context_analyst(
        timestamps=daily_index(5),
        event_labels=["holiday", "holiday"],
        run_id="test-mismatch",
        generated_at=datetime(2021, 1, 8, tzinfo=UTC),
        trajectory_path=tmp_path / "mismatch.jsonl",
    )
    assert state.status == "failed"
    assert state.error_type == "InvalidContextInput"
    report = state.report
    assert report is not None
    assert report.context_available is False
    assert "unavailable" in (report.unavailable_reason or "").lower()
    assert report.possible_explanations == []
    assert report.forecast_adjusted is False


def test_inspect_tool_does_not_fill_blank_labels() -> None:
    env = run_inspect_context_tool(
        timestamps=daily_index(3),
        event_labels=["", None, "  "],
    )
    assert env.ok is True
    assert env.payload["context_available"] is False
    assert env.payload["windows"] == []


def test_finding_rejects_causal_assertion() -> None:
    with pytest.raises(ValueError, match="causality"):
        ContextFinding(
            kind="observed_fact",
            statement="The promotion caused demand to rise.",
            evidence_ids=["E1"],
            uncertainty="low",
            why_uncertainty="n/a",
            asserts_causality=True,
        )
    with pytest.raises(ValueError, match="causal"):
        ContextFinding(
            kind="observed_fact",
            statement="The promotion caused demand to rise.",
            evidence_ids=["E1"],
            uncertainty="low",
            why_uncertainty="n/a",
        )
