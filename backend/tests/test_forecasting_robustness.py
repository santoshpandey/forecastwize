from __future__ import annotations

import inspect
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from app.forecasting.robustness import (
    EXP010_LAST_TO_EARLIER_VETO,
    analyze_backtest_robustness,
    recent_and_earlier,
)
from app.tools.forecasting_tools import CandidateEvalRow
from app.tools.robustness_tools import (
    ANALYZE_BACKTEST_ROBUSTNESS,
    reject_unknown_robustness_tool,
    run_analyze_backtest_robustness_tool,
)

from tests.ts_fixtures import daily_index


def _row(
    model_id: str,
    fold_wis: list[float | None],
    *,
    official: float | None = None,
    failed: int = 0,
) -> CandidateEvalRow:
    finite = [v for v in fold_wis if v is not None]
    planned = len(fold_wis)
    if official is not None:
        official_wis = official
    elif finite:
        official_wis = sum(finite) / len(finite)
    else:
        official_wis = None
    if failed:
        official_wis = None
    return CandidateEvalRow(
        model_id=model_id,
        official_wis=official_wis,
        wis_completed_only=official_wis,
        n_folds_planned=planned,
        n_folds_completed=len(finite),
        n_folds_failed=failed,
        rank=None,
        fold_wis=fold_wis,
        fold_train_sizes=list(range(10, 10 + planned)),
        eligible=official_wis is not None and failed == 0 and planned > 0,
    )


def test_robustness_source_has_no_holdout_or_llm() -> None:
    from app.forecasting import robustness
    from app.tools import robustness_tools

    for module in (robustness, robustness_tools):
        text = inspect.getsource(module).lower()
        assert "score_holdout" not in text
        assert "split_train_holdout" not in text
        assert "import fastapi" not in text
        assert "import openai" not in text
        assert "yhat =" not in text


def test_unknown_robustness_tool_is_rejected() -> None:
    with pytest.raises(Exception, match="Unknown tool"):
        reject_unknown_robustness_tool("invent_wis")
    reject_unknown_robustness_tool(ANALYZE_BACKTEST_ROBUSTNESS)


def test_recent_vs_earlier_ratio() -> None:
    recent, earlier, ratio = recent_and_earlier([0.3, 0.3, 0.3, 0.3, 5.1])
    assert earlier == pytest.approx(0.3)
    assert recent == pytest.approx(5.1)
    assert ratio == pytest.approx(17.0)


def test_veto_blocks_last_fold_collapse_at_frozen_r() -> None:
    rows = [
        _row("ets", [0.38, 0.36, 0.27, 0.30, 5.58], official=1.38),
        _row("seasonal_naive", [1.37, 0.41, 0.52, 0.37, 5.79], official=1.69),
        _row("arima", [0.21, 0.16, 0.21, 0.24, 8.37], official=1.84),
        _row("naive", [4.53, 3.10, 2.85, 3.32, 3.71], official=3.50),
    ]
    analysis = analyze_backtest_robustness(rows, threshold_r=EXP010_LAST_TO_EARLIER_VETO)
    by_id = {item.model_id: item for item in analysis.models}
    assert EXP010_LAST_TO_EARLIER_VETO == 5.0
    assert by_id["ets"].vetoed is True
    assert by_id["seasonal_naive"].vetoed is True
    assert by_id["arima"].vetoed is True
    assert by_id["naive"].vetoed is False
    assert analysis.selected_model_id == "naive"
    assert analysis.selection_rule == "official_backtest_wis"
    assert analysis.used_last_fold_fallback is False


def test_stable_arima_is_not_vetoed() -> None:
    rows = [
        _row("arima", [0.05, 0.06, 0.05, 0.07, 0.06], official=0.056),
        _row("ets", [0.14, 0.07, 0.06, 0.08, 0.07], official=0.084),
        _row("naive", [0.79, 0.45, 0.32, 0.37, 0.36], official=0.46),
    ]
    analysis = analyze_backtest_robustness(rows)
    by_id = {item.model_id: item for item in analysis.models}
    assert by_id["arima"].vetoed is False
    assert by_id["arima"].recent_vs_earlier_ratio is not None
    assert by_id["arima"].recent_vs_earlier_ratio < EXP010_LAST_TO_EARLIER_VETO
    assert analysis.selected_model_id == "arima"


def test_all_vetoed_uses_last_fold_fallback() -> None:
    rows = [
        _row("ets", [0.2, 0.2, 0.2, 0.2, 3.0], official=0.76),
        _row("naive", [0.3, 0.3, 0.3, 0.3, 2.0], official=0.84),
    ]
    analysis = analyze_backtest_robustness(rows)
    assert all(item.vetoed for item in analysis.models)
    assert analysis.used_last_fold_fallback is True
    assert analysis.selection_rule == "last_fold_wis_fallback"
    assert analysis.selected_model_id == "naive"


def test_planned_fold_failure_is_not_selectable() -> None:
    rows = [
        _row("ets", [0.2, None], official=None, failed=1),
        _row("naive", [0.4, 0.4], official=0.4),
    ]
    analysis = analyze_backtest_robustness(rows)
    by_id = {item.model_id: item for item in analysis.models}
    assert by_id["ets"].official_eligible is False
    assert by_id["ets"].selectable is False
    assert by_id["ets"].veto_reason == "planned_fold_failed"
    assert analysis.selected_model_id == "naive"


def test_single_fold_cannot_veto() -> None:
    rows = [_row("naive", [0.5], official=0.5)]
    analysis = analyze_backtest_robustness(rows)
    assert analysis.models[0].vetoed is False
    assert analysis.models[0].recent_vs_earlier_ratio is None
    assert analysis.selected_model_id == "naive"


def test_tool_envelope_and_repeatability() -> None:
    rows = [
        _row("ets", [0.3, 0.3, 0.3, 0.3, 5.1], official=1.26),
        _row("naive", [1.0, 1.0, 1.0, 1.0, 1.1], official=1.02),
    ]
    first = run_analyze_backtest_robustness_tool(rows)
    second = run_analyze_backtest_robustness_tool(rows)
    assert first.ok is True
    assert first.payload == second.payload
    assert first.payload["selected_model_id"] == "naive"
    assert first.payload["threshold_r"] == EXP010_LAST_TO_EARLIER_VETO


def test_exp009_train_table_justifies_frozen_r() -> None:
    path = (
        Path(__file__).resolve().parents[2]
        / "evaluation"
        / "artifacts"
        / "EXP-009-ets-arima-min-train"
        / "agent.json"
    )
    payload = json.loads(path.read_text(encoding="utf-8"))
    arima_win_cases = {"001", "002", "003", "004", "005", "008", "009", "011"}
    for case in payload["per_case"]:
        rows = []
        for item in case["backtest"]:
            rows.append(
                _row(
                    item["model_id"],
                    list(item.get("fold_wis") or []),
                    official=item.get("official_wis"),
                    failed=int(item.get("n_folds_failed") or 0),
                )
            )
        analysis = analyze_backtest_robustness(rows)
        by_id = {item.model_id: item for item in analysis.models}
        if case["case_id"] == "012":
            assert by_id["ets"].vetoed is True
            assert by_id["ets"].recent_vs_earlier_ratio is not None
            assert by_id["ets"].recent_vs_earlier_ratio >= EXP010_LAST_TO_EARLIER_VETO
            assert analysis.selected_model_id != "ets"
        if case["case_id"] in arima_win_cases:
            assert by_id["arima"].official_eligible is True
            assert by_id["arima"].vetoed is False
            assert analysis.selected_model_id == "arima"


def test_strategist_exp010_does_not_select_collapsed_ets(tmp_path: Path) -> None:
    from app.agents.forecast_strategist import DatasetDiagnostics, run_forecast_strategist

    n = 80
    values = []
    for i in range(n):
        seasonal = 2.0 if (i % 7) < 3 else -2.0
        if i < 60:
            values.append(10.0 + 0.02 * i + seasonal)
        else:
            values.append(40.0 - seasonal + (i % 3))
    state = run_forecast_strategist(
        daily_index(n),
        values,
        horizon=7,
        frequency="D",
        diagnostics=DatasetDiagnostics(
            n_observations=n,
            frequency="D",
            seasonal_period=7,
            trend_detected=True,
            seasonality_detected=True,
            structural_break_detected=True,
            forecastability="limited",
            detective_evidence_ids=["E-diag"],
        ),
        candidate_model_ids=("naive", "ets", "arima"),
        seasonal_period=7,
        seed=12,
        generated_at=datetime(2021, 5, 1, tzinfo=UTC),
        trajectory_path=tmp_path / "r.jsonl",
        persist_trajectory=True,
        selection_policy="exp010",
    )
    assert state.status == "completed"
    assert state.report is not None
    assert any(
        item.tool_name == ANALYZE_BACKTEST_ROBUSTNESS for item in state.evidence.values()
    )
    assert state.report.selection_rule in {"official_backtest_wis", "last_fold_wis_fallback"}
    winner = state.report.recommended_strategy_id
    assert winner is not None
    win_row = next(row for row in state.report.comparison if row.model_id == winner)
    assert win_row.selectable is True
    assert win_row.vetoed is not True
