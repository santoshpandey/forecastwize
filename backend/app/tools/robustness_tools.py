"""Deterministic robustness analysis over backtest fold WIS. No holdout. No LLM."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from pydantic import BaseModel, ConfigDict

from app.forecasting.base import ForecastInterfaceError
from app.forecasting.robustness import (
    EXP010_LAST_TO_EARLIER_VETO,
    EXP010_RECENT_FOLD_COUNT,
    RobustnessAnalysis,
    analyze_backtest_robustness,
)
from app.tools.forecasting_tools import CandidateEvalRow

ANALYZE_BACKTEST_ROBUSTNESS = "analyze_backtest_robustness"
ROBUSTNESS_TOOL_NAMES = (ANALYZE_BACKTEST_ROBUSTNESS,)

JsonObject = dict[str, Any]


class RobustnessToolEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tool_name: str
    ok: bool
    payload: JsonObject
    error_type: str | None = None
    error_message: str | None = None


def reject_unknown_robustness_tool(name: str) -> None:
    if name not in ROBUSTNESS_TOOL_NAMES:
        allowed = ", ".join(ROBUSTNESS_TOOL_NAMES)
        msg = f"Unknown tool {name!r}. Approved robustness tools: {allowed}."
        raise ForecastInterfaceError(msg)


def run_analyze_backtest_robustness_tool(
    candidates: Sequence[CandidateEvalRow],
    *,
    threshold_r: float = EXP010_LAST_TO_EARLIER_VETO,
    recent_fold_count: int = EXP010_RECENT_FOLD_COUNT,
    origins_aligned: bool = False,
) -> RobustnessToolEnvelope:
    """Analyze training-fold WIS already returned by evaluate_candidates."""
    reject_unknown_robustness_tool(ANALYZE_BACKTEST_ROBUSTNESS)
    try:
        analysis = analyze_backtest_robustness(
            candidates,
            threshold_r=threshold_r,
            recent_fold_count=recent_fold_count,
            origins_aligned=origins_aligned,
        )
        return RobustnessToolEnvelope(
            tool_name=ANALYZE_BACKTEST_ROBUSTNESS,
            ok=True,
            payload=analysis.model_dump(mode="json"),
        )
    except (ForecastInterfaceError, ValueError) as exc:
        return RobustnessToolEnvelope(
            tool_name=ANALYZE_BACKTEST_ROBUSTNESS,
            ok=False,
            payload={"summary": str(exc)},
            error_type=type(exc).__name__,
            error_message=str(exc),
        )


def apply_robustness_to_rows(
    rows: list[CandidateEvalRow],
    analysis: RobustnessAnalysis,
) -> list[CandidateEvalRow]:
    """Copy veto/selectable flags onto comparison rows. Does not change official WIS."""
    by_id = {item.model_id: item for item in analysis.models}
    updated: list[CandidateEvalRow] = []
    for row in rows:
        stats = by_id.get(row.model_id)
        if stats is None:
            updated.append(row)
            continue
        payload = row.model_dump()
        payload["vetoed"] = stats.vetoed
        payload["veto_reason"] = stats.veto_reason
        payload["selectable"] = stats.selectable
        payload["recent_vs_earlier_ratio"] = stats.recent_vs_earlier_ratio
        payload["recent_fold_mean_wis"] = stats.recent_fold_mean_wis
        payload["earlier_fold_mean_wis"] = stats.earlier_fold_mean_wis
        if stats.vetoed:
            payload["rejection_reason"] = stats.veto_reason
        elif stats.selectable and analysis.selected_model_id == row.model_id:
            payload["rejection_reason"] = None
        elif stats.selectable and analysis.selected_model_id is not None:
            payload["rejection_reason"] = "higher_official_wis"
        updated.append(CandidateEvalRow.model_validate(payload))
    return updated
