"""Deterministic context/event inspection. Records labels as provided. No yhat. No causality.

Does not invent events, modify labels, or adjust forecasts. No FastAPI. No LLM.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any, Literal

import pandas as pd
from pydantic import BaseModel, ConfigDict, Field, field_serializer

from app.forecasting.base import ForecastInterfaceError

INSPECT_CONTEXT = "inspect_context"
CONTEXT_TOOL_NAMES = (INSPECT_CONTEXT,)

EventKind = Literal[
    "promotion",
    "holiday",
    "campaign",
    "price_change",
    "stockout",
    "product_launch",
    "external_business_event",
    "unrecognized",
]
LabelSource = Literal["event", "context", "record"]
JsonObject = dict[str, Any]

_KIND_ALIASES: dict[str, EventKind] = {
    "promotion": "promotion",
    "promo": "promotion",
    "holiday": "holiday",
    "holidays": "holiday",
    "campaign": "campaign",
    "price change": "price_change",
    "price_change": "price_change",
    "pricechange": "price_change",
    "stockout": "stockout",
    "stock out": "stockout",
    "stock_out": "stockout",
    "product launch": "product_launch",
    "product_launch": "product_launch",
    "launch": "product_launch",
    "external business event": "external_business_event",
    "external_business_event": "external_business_event",
    "external": "external_business_event",
}

_KNOWN_KINDS: tuple[EventKind, ...] = (
    "promotion",
    "holiday",
    "campaign",
    "price_change",
    "stockout",
    "product_launch",
    "external_business_event",
)


def _to_utc_iso(value: datetime) -> str:
    aware = value if value.tzinfo is not None else value.replace(tzinfo=UTC)
    return aware.astimezone(UTC).isoformat().replace("+00:00", "Z")


class ContextualRecord(BaseModel):
    """Caller-supplied labeled window or point. Missing labels are not invented."""

    model_config = ConfigDict(extra="forbid")

    timestamp: datetime | None = None
    start: datetime | None = None
    end: datetime | None = None
    event_label: str | None = None
    context_label: str | None = None


class InspectContextSpec(BaseModel):
    """Allowlisted inspect arguments. Unknown fields are rejected."""

    model_config = ConfigDict(extra="forbid")

    notes_provided: bool = False
    notes_character_count: int | None = None


class LabeledWindow(BaseModel):
    """Consecutive identical non-empty labels. Classification is lexical, not causal."""

    model_config = ConfigDict(extra="forbid")

    source: LabelSource
    raw_label: str
    event_kind: EventKind
    n_steps: int
    start_index: int | None = None
    end_index: int | None = None
    start: datetime | None = None
    end: datetime | None = None

    @field_serializer("start", "end")
    def serialize_bound(self, value: datetime | None) -> str | None:
        if value is None:
            return None
        return _to_utc_iso(value)


class InspectContextResult(BaseModel):
    """Observed label inventory. Does not explain series movement or emit forecasts."""

    model_config = ConfigDict(extra="forbid")

    context_available: bool
    unavailable_reason: str | None
    n_event_non_null: int
    n_context_non_null: int
    n_record_labels: int
    windows: list[LabeledWindow]
    recognized_kinds: list[EventKind]
    unrecognized_labels: list[str]
    notes_provided: bool
    notes_character_count: int | None
    summary: str
    limitations: list[str] = Field(default_factory=list)


class ContextToolEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tool_name: str
    ok: bool
    payload: JsonObject
    error_type: str | None = None
    error_message: str | None = None


def classify_event_label(raw: str) -> EventKind:
    key = " ".join(raw.strip().lower().replace("_", " ").replace("-", " ").split())
    return _KIND_ALIASES.get(key, "unrecognized")


def reject_unknown_context_tool(name: str) -> None:
    if name not in CONTEXT_TOOL_NAMES:
        allowed = ", ".join(CONTEXT_TOOL_NAMES)
        msg = f"Unknown tool {name!r}. Approved context tools: {allowed}."
        raise ForecastInterfaceError(msg)


def run_named_context_tool(
    name: str,
    *,
    timestamps: pd.Series | pd.DatetimeIndex | Sequence[datetime] | None = None,
    event_labels: Sequence[object] | pd.Series | None = None,
    context_labels: Sequence[object] | pd.Series | None = None,
    records: Sequence[ContextualRecord] | None = None,
    spec: InspectContextSpec | None = None,
) -> ContextToolEnvelope:
    reject_unknown_context_tool(name)
    return run_inspect_context_tool(
        timestamps=timestamps,
        event_labels=event_labels,
        context_labels=context_labels,
        records=records,
        spec=spec,
    )


def run_inspect_context_tool(
    *,
    timestamps: pd.Series | pd.DatetimeIndex | Sequence[datetime] | None = None,
    event_labels: Sequence[object] | pd.Series | None = None,
    context_labels: Sequence[object] | pd.Series | None = None,
    records: Sequence[ContextualRecord] | None = None,
    spec: InspectContextSpec | None = None,
) -> ContextToolEnvelope:
    """Extract labeled windows. Empty/missing labels are not filled. No series values used."""
    options = spec if spec is not None else InspectContextSpec()
    mismatch = _length_mismatch(timestamps, event_labels, context_labels)
    if mismatch is not None:
        return ContextToolEnvelope(
            tool_name=INSPECT_CONTEXT,
            ok=False,
            payload={"summary": mismatch, "context_available": False},
            error_type="InvalidContextInput",
            error_message=mismatch,
        )
    result = inspect_context(
        timestamps=timestamps,
        event_labels=event_labels,
        context_labels=context_labels,
        records=records,
        spec=options,
    )
    return ContextToolEnvelope(
        tool_name=INSPECT_CONTEXT,
        ok=True,
        payload=result.model_dump(mode="json"),
    )


def inspect_context(
    *,
    timestamps: pd.Series | pd.DatetimeIndex | Sequence[datetime] | None = None,
    event_labels: Sequence[object] | pd.Series | None = None,
    context_labels: Sequence[object] | pd.Series | None = None,
    records: Sequence[ContextualRecord] | None = None,
    spec: InspectContextSpec | None = None,
) -> InspectContextResult:
    options = spec if spec is not None else InspectContextSpec()
    stamps = _as_timestamp_list(timestamps)
    event_raw = _as_label_list(event_labels)
    context_raw = _as_label_list(context_labels)
    record_list = list(records) if records is not None else []

    windows: list[LabeledWindow] = []
    windows.extend(_windows_from_series(event_raw, stamps, source="event"))
    windows.extend(_windows_from_series(context_raw, stamps, source="context"))
    windows.extend(_windows_from_records(record_list))

    n_event = sum(1 for item in event_raw if _raw_or_none(item) is not None)
    n_context = sum(1 for item in context_raw if _raw_or_none(item) is not None)
    n_records = 0
    for rec in record_list:
        if _raw_or_none(rec.event_label) is not None:
            n_records += 1
        if _raw_or_none(rec.context_label) is not None:
            n_records += 1

    context_available = bool(windows)
    recognized = sorted(
        {item.event_kind for item in windows if item.event_kind != "unrecognized"},
        key=_KNOWN_KINDS.index,
    )
    unrecognized = sorted({item.raw_label for item in windows if item.event_kind == "unrecognized"})
    unavailable = None
    if not context_available:
        unavailable = "No context or event data was provided. Contextual analysis is unavailable."
        summary = unavailable
    else:
        summary = (
            f"{len(windows)} labeled window(s); "
            f"event_non_null={n_event}; context_non_null={n_context}; "
            f"record_labels={n_records}."
        )
    limitations = [
        "Labels are recorded as provided. Missing labels are not invented or filled.",
        "A present label is an observed fact about the input, not a causal finding.",
        "This tool does not read series values and does not adjust forecasts.",
        "Free-text notes are not parsed into event types.",
    ]
    return InspectContextResult(
        context_available=context_available,
        unavailable_reason=unavailable,
        n_event_non_null=n_event,
        n_context_non_null=n_context,
        n_record_labels=n_records,
        windows=windows,
        recognized_kinds=list(recognized),
        unrecognized_labels=unrecognized,
        notes_provided=options.notes_provided,
        notes_character_count=options.notes_character_count,
        summary=summary,
        limitations=limitations,
    )


def _length_mismatch(
    timestamps: pd.Series | pd.DatetimeIndex | Sequence[datetime] | None,
    event_labels: Sequence[object] | pd.Series | None,
    context_labels: Sequence[object] | pd.Series | None,
) -> str | None:
    n_ts = _optional_length(timestamps)
    n_event = _optional_length(event_labels)
    n_context = _optional_length(context_labels)
    if n_ts is not None and n_event is not None and n_ts != n_event:
        return f"event_labels length {n_event} != timestamps length {n_ts}"
    if n_ts is not None and n_context is not None and n_ts != n_context:
        return f"context_labels length {n_context} != timestamps length {n_ts}"
    if n_event is not None and n_context is not None and n_event != n_context:
        return f"event_labels length {n_event} != context_labels length {n_context}"
    return None


def _optional_length(values: object | None) -> int | None:
    if values is None:
        return None
    return len(values)  # type: ignore[arg-type]


def _as_timestamp_list(
    timestamps: pd.Series | pd.DatetimeIndex | Sequence[datetime] | None,
) -> list[datetime | None]:
    if timestamps is None:
        return []
    return [_as_utc(item) for item in timestamps]


def _as_label_list(labels: Sequence[object] | pd.Series | None) -> list[object]:
    if labels is None:
        return []
    return list(labels)


def _windows_from_series(
    labels: list[object],
    stamps: list[datetime | None],
    *,
    source: LabelSource,
) -> list[LabeledWindow]:
    out: list[LabeledWindow] = []
    n = len(labels)
    index = 0
    while index < n:
        raw = _raw_or_none(labels[index])
        if raw is None:
            index += 1
            continue
        end = index + 1
        while end < n and _raw_or_none(labels[end]) == raw:
            end += 1
        last = end - 1
        start_ts = stamps[index] if index < len(stamps) else None
        end_ts = stamps[last] if last < len(stamps) else None
        out.append(
            LabeledWindow(
                source=source,
                raw_label=raw,
                event_kind=classify_event_label(raw),
                n_steps=end - index,
                start_index=index,
                end_index=last,
                start=start_ts,
                end=end_ts,
            )
        )
        index = end
    return out


def _windows_from_records(records: list[ContextualRecord]) -> list[LabeledWindow]:
    out: list[LabeledWindow] = []
    for rec in records:
        event_raw = _raw_or_none(rec.event_label)
        context_raw = _raw_or_none(rec.context_label)
        start = rec.start if rec.start is not None else rec.timestamp
        end = rec.end if rec.end is not None else rec.timestamp
        if event_raw is not None:
            out.append(
                LabeledWindow(
                    source="record",
                    raw_label=event_raw,
                    event_kind=classify_event_label(event_raw),
                    n_steps=1,
                    start=_as_utc(start),
                    end=_as_utc(end),
                )
            )
        if context_raw is not None:
            out.append(
                LabeledWindow(
                    source="record",
                    raw_label=context_raw,
                    event_kind=classify_event_label(context_raw),
                    n_steps=1,
                    start=_as_utc(start),
                    end=_as_utc(end),
                )
            )
    return out


def _raw_or_none(value: object) -> str | None:
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    if isinstance(value, str) and not value.strip():
        return None
    text = str(value).strip()
    if not text or text.lower() in {"nan", "none", "nat"}:
        return None
    return text


def _as_utc(value: object) -> datetime | None:
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    ts = pd.Timestamp(value)
    if pd.isna(ts):
        return None
    if ts.tzinfo is None:
        ts = ts.tz_localize("UTC")
    else:
        ts = ts.tz_convert("UTC")
    converted = ts.to_pydatetime()
    if converted.tzinfo is None:
        return converted.replace(tzinfo=UTC)
    return converted.astimezone(UTC)
