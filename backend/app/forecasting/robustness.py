"""Training-fold robustness stats for model selection. No holdout. No LLM. No yhat."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Literal

import numpy as np
from pydantic import BaseModel, ConfigDict, Field

# Frozen from EXP-009 *training* fold WIS tables before any EXP-010 catalog run.
# 012 ETS last/earlier ≈ 17; ARIMA wins on 001–005/008/009/011 had ratios ≤ 1.53.
# Do not retune after seeing holdout WIS.
EXP010_LAST_TO_EARLIER_VETO = 5.0
EXP010_RECENT_FOLD_COUNT = 1

SelectionPolicy = Literal["default", "exp010"]
# Official advanced path after EXP-010 promotion. Shared-origin parity remains
# available as selection_policy='default' (historical EXP-008 / EXP-009 planner).
DEFAULT_SELECTION_POLICY: SelectionPolicy = "exp010"
HISTORICAL_SHARED_SELECTION_POLICY: SelectionPolicy = "default"
RobustnessSelectionRule = Literal[
    "official_backtest_wis",
    "last_fold_wis_fallback",
    "none",
]


class ModelRobustnessRow(BaseModel):
    """Per-model training-fold robustness. Official WIS is copied, not recomputed."""

    model_config = ConfigDict(extra="forbid")

    model_id: str
    official_wis: float | None
    fold_wis: list[float | None] = Field(default_factory=list)
    fold_train_sizes: list[int] = Field(default_factory=list)
    n_folds_failed: int
    mean_wis: float | None = None
    median_wis: float | None = None
    std_wis: float | None = None
    min_wis: float | None = None
    max_wis: float | None = None
    recent_fold_mean_wis: float | None = None
    earlier_fold_mean_wis: float | None = None
    recent_vs_earlier_ratio: float | None = None
    n_folds_won: int | None = None
    n_folds_lost: int | None = None
    pct_folds_won: float | None = None
    official_eligible: bool
    vetoed: bool
    veto_reason: str | None = None
    selectable: bool


class RobustnessAnalysis(BaseModel):
    """Deterministic gate over official backtest WIS. Does not emit a forecast."""

    model_config = ConfigDict(extra="forbid")

    threshold_r: float
    recent_fold_count: int
    origins_aligned: bool
    selected_model_id: str | None
    selection_rule: RobustnessSelectionRule
    used_last_fold_fallback: bool
    models: list[ModelRobustnessRow]


def finite_fold_wis(fold_wis: Sequence[float | None]) -> list[float]:
    return [float(value) for value in fold_wis if value is not None and np.isfinite(value)]


def fold_wis_summary(fold_wis: Sequence[float | None]) -> dict[str, float | None]:
    finite = finite_fold_wis(fold_wis)
    if not finite:
        return {
            "mean_wis": None,
            "median_wis": None,
            "std_wis": None,
            "min_wis": None,
            "max_wis": None,
        }
    arr = np.asarray(finite, dtype=float)
    std = float(np.std(arr, ddof=1)) if arr.size >= 2 else None
    return {
        "mean_wis": float(np.mean(arr)),
        "median_wis": float(np.median(arr)),
        "std_wis": std,
        "min_wis": float(np.min(arr)),
        "max_wis": float(np.max(arr)),
    }


def recent_and_earlier(
    fold_wis: Sequence[float | None],
    *,
    recent_fold_count: int = EXP010_RECENT_FOLD_COUNT,
) -> tuple[float | None, float | None, float | None]:
    """Last `recent_fold_count` completed folds vs the rest. Training folds only."""
    if recent_fold_count < 1:
        msg = "recent_fold_count must be >= 1"
        raise ValueError(msg)
    finite = finite_fold_wis(fold_wis)
    if len(finite) < recent_fold_count + 1:
        return (None, None, None)
    recent = finite[-recent_fold_count:]
    earlier = finite[:-recent_fold_count]
    recent_mean = float(np.mean(recent))
    earlier_mean = float(np.mean(earlier))
    ratio = None if earlier_mean == 0.0 else recent_mean / earlier_mean
    return recent_mean, earlier_mean, ratio


def official_eligible(
    *,
    n_folds_planned: int,
    n_folds_failed: int,
    official_wis: float | None,
) -> bool:
    return n_folds_planned > 0 and n_folds_failed == 0 and official_wis is not None


def instability_veto(
    *,
    official_ok: bool,
    recent_vs_earlier_ratio: float | None,
    threshold_r: float = EXP010_LAST_TO_EARLIER_VETO,
) -> tuple[bool, str | None]:
    """Veto when last/earlier fold WIS is defined and >= R. Does not use holdout."""
    if not official_ok:
        return False, None
    if recent_vs_earlier_ratio is None:
        return False, None
    if recent_vs_earlier_ratio >= threshold_r:
        return True, "last_to_earlier_ratio"
    return False, None


def analyze_backtest_robustness(
    rows: Sequence[object],
    *,
    threshold_r: float = EXP010_LAST_TO_EARLIER_VETO,
    recent_fold_count: int = EXP010_RECENT_FOLD_COUNT,
    origins_aligned: bool = False,
) -> RobustnessAnalysis:
    """Score training-fold stability and select among models that pass the veto.

    ``rows`` must expose model_id, official_wis, fold_wis, fold_train_sizes,
    n_folds_planned, n_folds_failed. Official WIS is not recalculated.
    """
    prepared: list[ModelRobustnessRow] = []
    for row in rows:
        fold_wis = list(getattr(row, "fold_wis"))
        official = getattr(row, "official_wis")
        n_planned = int(getattr(row, "n_folds_planned"))
        n_failed = int(getattr(row, "n_folds_failed"))
        ok = official_eligible(
            n_folds_planned=n_planned,
            n_folds_failed=n_failed,
            official_wis=official,
        )
        summary = fold_wis_summary(fold_wis)
        recent, earlier, ratio = recent_and_earlier(
            fold_wis, recent_fold_count=recent_fold_count
        )
        vetoed, veto_reason = instability_veto(
            official_ok=ok,
            recent_vs_earlier_ratio=ratio,
            threshold_r=threshold_r,
        )
        if not ok:
            selectable = False
            if n_planned == 0:
                reject = "insufficient_history"
            elif n_failed > 0:
                reject = "planned_fold_failed"
            else:
                reject = "official_wis_undefined"
            veto_reason = veto_reason or reject
        else:
            selectable = not vetoed
        prepared.append(
            ModelRobustnessRow(
                model_id=str(getattr(row, "model_id")),
                official_wis=None if official is None else float(official),
                fold_wis=fold_wis,
                fold_train_sizes=list(getattr(row, "fold_train_sizes", [])),
                n_folds_failed=n_failed,
                mean_wis=summary["mean_wis"],
                median_wis=summary["median_wis"],
                std_wis=summary["std_wis"],
                min_wis=summary["min_wis"],
                max_wis=summary["max_wis"],
                recent_fold_mean_wis=recent,
                earlier_fold_mean_wis=earlier,
                recent_vs_earlier_ratio=ratio,
                official_eligible=ok,
                vetoed=vetoed,
                veto_reason=None if selectable else veto_reason,
                selectable=selectable,
            )
        )
    if origins_aligned:
        _assign_aligned_fold_trophies(prepared)
    selected, rule, fallback = _select(prepared)
    return RobustnessAnalysis(
        threshold_r=threshold_r,
        recent_fold_count=recent_fold_count,
        origins_aligned=origins_aligned,
        selected_model_id=selected,
        selection_rule=rule,
        used_last_fold_fallback=fallback,
        models=prepared,
    )


def _assign_aligned_fold_trophies(rows: list[ModelRobustnessRow]) -> None:
    lengths = {len(row.fold_wis) for row in rows}
    if len(lengths) != 1:
        return
    n_folds = next(iter(lengths))
    if n_folds < 1:
        return
    wins = {row.model_id: 0 for row in rows}
    losses = {row.model_id: 0 for row in rows}
    for fold_id in range(n_folds):
        scored: list[tuple[str, float]] = []
        for row in rows:
            value = row.fold_wis[fold_id]
            if value is not None and np.isfinite(value):
                scored.append((row.model_id, float(value)))
        if not scored:
            continue
        best = min(item[1] for item in scored)
        winners = {model_id for model_id, wis in scored if wis == best}
        for model_id, _wis in scored:
            if model_id in winners:
                wins[model_id] += 1
            else:
                losses[model_id] += 1
    for row in rows:
        n_won = wins[row.model_id]
        n_lost = losses[row.model_id]
        played = n_won + n_lost
        row.n_folds_won = n_won
        row.n_folds_lost = n_lost
        row.pct_folds_won = None if played == 0 else n_won / played


def _select(
    rows: list[ModelRobustnessRow],
) -> tuple[str | None, RobustnessSelectionRule, bool]:
    survivors = [row for row in rows if row.selectable and row.official_wis is not None]
    survivors.sort(
        key=lambda row: (
            row.official_wis if row.official_wis is not None else 10**9,
            row.model_id,
        )
    )
    if survivors:
        return survivors[0].model_id, "official_backtest_wis", False
    fallback = [
        row
        for row in rows
        if row.official_eligible and row.recent_fold_mean_wis is not None
    ]
    fallback.sort(
        key=lambda row: (
            row.recent_fold_mean_wis if row.recent_fold_mean_wis is not None else 10**9,
            row.model_id,
        )
    )
    if fallback:
        return fallback[0].model_id, "last_fold_wis_fallback", True
    return None, "none", False
