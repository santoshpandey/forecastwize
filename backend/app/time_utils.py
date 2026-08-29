from __future__ import annotations

from datetime import UTC, datetime


def utc_now() -> datetime:
    """UTC clock used for persisted/API timestamps (ISO 8601)."""
    return datetime.now(UTC)
