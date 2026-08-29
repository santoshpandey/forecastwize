from __future__ import annotations

import re
from pathlib import Path
from uuid import uuid4

_ID_RE = re.compile(r"^(ds|fc|run|ev)_[0-9a-f]{32}$")
_UNSAFE_FILENAME = re.compile(r"[^A-Za-z0-9._-]+")


def new_prefixed_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex}"


def is_safe_resource_id(value: str) -> bool:
    return bool(_ID_RE.fullmatch(value))


def require_resource_id(value: str) -> str:
    from app.api.errors import ApiError

    if not is_safe_resource_id(value):
        raise ApiError(404, "not_found", "Resource was not found.")
    return value


def sanitize_upload_filename(raw: str) -> str:
    """Return a basename-only .csv name. Reject path traversal and non-csv names."""
    from app.api.errors import ApiError

    candidate = raw.replace("\\", "/").strip()
    if not candidate:
        raise ApiError(422, "invalid_filename", "A .csv filename is required.")
    if candidate.startswith("/") or (len(candidate) > 1 and candidate[1] == ":"):
        raise ApiError(422, "invalid_filename", "Absolute paths are not allowed.")
    if ".." in Path(candidate).parts or ".." in candidate.split("/"):
        raise ApiError(422, "invalid_filename", "Path traversal is not allowed.")
    base = Path(candidate).name
    if not base or base in {".", ".."}:
        raise ApiError(422, "invalid_filename", "A .csv filename is required.")
    cleaned = _UNSAFE_FILENAME.sub("_", base).strip("._")
    if not cleaned.lower().endswith(".csv"):
        raise ApiError(422, "invalid_filename", "Only .csv uploads are allowed.")
    if cleaned.lower() == ".csv" or len(cleaned) < 5:
        raise ApiError(422, "invalid_filename", "A .csv filename is required.")
    return cleaned
