from __future__ import annotations

import json
import logging
import re
import sys
from datetime import UTC, datetime
from typing import Any

from app.config import Settings
from app.request_context import get_request_id

_STANDARD_RECORD_ATTRS = frozenset(
    {
        "name",
        "msg",
        "args",
        "levelname",
        "levelno",
        "pathname",
        "filename",
        "module",
        "exc_info",
        "exc_text",
        "stack_info",
        "lineno",
        "funcName",
        "created",
        "msecs",
        "relativeCreated",
        "thread",
        "threadName",
        "processName",
        "process",
        "taskName",
        "message",
    }
)

_SECRET_KEY_FRAGMENTS = ("key", "secret", "token", "password", "authorization")
_SECRET_IN_TEXT = re.compile(r"(?i)(api[_-]?key|token|password|secret|authorization)\s*[:=]\s*\S+")
_SK_PATTERN = re.compile(r"sk-[A-Za-z0-9]{10,}")


class RequestIdLogFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        if not hasattr(record, "request_id") or getattr(record, "request_id") in (None, ""):
            record.request_id = get_request_id() or "-"
        return True


def _redact(value: Any, key: str) -> Any:
    lowered = key.lower()
    if any(fragment in lowered for fragment in _SECRET_KEY_FRAGMENTS):
        return "[redacted]"
    return value


def _redact_text(value: str) -> str:
    out = _SECRET_IN_TEXT.sub(lambda match: f"{match.group(1)}=[redacted]", value)
    return _SK_PATTERN.sub("[redacted]", out)


class JsonLogFormatter(logging.Formatter):
    """One JSON object per line. Extra fields are merged; secret-like keys are redacted."""

    def format(self, record: logging.LogRecord) -> str:
        timestamp = datetime.now(UTC).isoformat().replace("+00:00", "Z")
        payload: dict[str, Any] = {
            "timestamp": timestamp,
            "level": record.levelname,
            "logger": record.name,
            "message": _redact_text(record.getMessage()),
        }
        for key, value in record.__dict__.items():
            if key in _STANDARD_RECORD_ATTRS:
                continue
            payload[key] = _redact(value, key)
            if isinstance(payload[key], str):
                payload[key] = _redact_text(payload[key])
        if record.exc_info:
            payload["exception"] = _redact_text(self.formatException(record.exc_info))
        return json.dumps(payload, default=str)


def configure_logging(settings: Settings) -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonLogFormatter())
    handler.addFilter(RequestIdLogFilter())
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.addFilter(RequestIdLogFilter())
    root.setLevel(settings.log_level)
    logging.getLogger("uvicorn.access").setLevel(settings.log_level)
