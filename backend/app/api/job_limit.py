"""Cap concurrent background runs and evaluations. No FastAPI imports in callers' math."""

from __future__ import annotations

import threading

from app.api.errors import ApiError
from app.config import get_settings

_lock = threading.Lock()
_inflight = 0


def acquire_background_job() -> None:
    """Reserve a slot. Callers must release in a finally block."""
    global _inflight
    cap = get_settings().max_inflight_jobs
    with _lock:
        if _inflight >= cap:
            raise ApiError(
                429,
                "too_many_jobs",
                "Too many background jobs are already running. Retry later.",
            )
        _inflight += 1


def release_background_job() -> None:
    global _inflight
    with _lock:
        if _inflight > 0:
            _inflight -= 1


def reset_background_jobs_for_tests() -> None:
    global _inflight
    with _lock:
        _inflight = 0
