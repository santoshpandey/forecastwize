from __future__ import annotations

import json
import logging
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from app.api.datasets import require_upload_content_length
from app.api.errors import ApiError
from app.api.evaluations import _changelog_document_path
from app.api.job_limit import (
    acquire_background_job,
    release_background_job,
    reset_background_jobs_for_tests,
)
from app.api.store import FileStore
from app.config import Settings, get_settings
from app.structured_logging import JsonLogFormatter


def test_upload_requires_content_length() -> None:
    request = SimpleNamespace(headers={})
    with pytest.raises(ApiError) as exc:
        require_upload_content_length(request, Settings(max_upload_bytes=100))
    assert exc.value.status_code == 411
    assert exc.value.error_code == "length_required"


def test_upload_rejects_declared_oversize() -> None:
    request = SimpleNamespace(headers={"content-length": "200"})
    with pytest.raises(ApiError) as exc:
        require_upload_content_length(request, Settings(max_upload_bytes=100))
    assert exc.value.status_code == 413
    assert exc.value.error_code == "payload_too_large"


def test_job_limit_rejects_when_full(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MAX_INFLIGHT_JOBS", "1")
    get_settings.cache_clear()
    reset_background_jobs_for_tests()
    try:
        acquire_background_job()
        with pytest.raises(ApiError) as exc:
            acquire_background_job()
        assert exc.value.status_code == 429
        assert exc.value.error_code == "too_many_jobs"
        release_background_job()
        acquire_background_job()
    finally:
        reset_background_jobs_for_tests()
        get_settings.cache_clear()


def test_store_refuses_path_escape(tmp_path: Path) -> None:
    store = FileStore(tmp_path)
    with pytest.raises(ApiError) as exc:
        store.assert_under(tmp_path / "datasets", tmp_path.parent / "evil.csv")
    assert exc.value.error_code == "storage_error"
    with pytest.raises(ApiError):
        store.contained_file(tmp_path / "datasets", "../evil.csv")


def test_changelog_path_stays_under_docs() -> None:
    path = _changelog_document_path()
    assert path.name == "changelog.md"
    assert path.parent.name == "docs"


def test_log_formatter_redacts_secrets_in_message_and_exception() -> None:
    formatter = JsonLogFormatter()
    record = logging.LogRecord(
        name="test",
        level=logging.ERROR,
        pathname=__file__,
        lineno=1,
        msg="failed api_key=sk-abcdefghijklmnopqrstuvwxyz",
        args=(),
        exc_info=None,
    )
    payload = json.loads(formatter.format(record))
    assert "sk-abcdefghijklmnopqrstuvwxyz" not in payload["message"]
    assert "[redacted]" in payload["message"]

    try:
        raise RuntimeError("leak sk-abcdefghijklmnopqrstuvwxyz")
    except RuntimeError:
        record.exc_info = sys.exc_info()
    payload = json.loads(formatter.format(record))
    assert "exception" in payload
    assert "sk-abcdefghijklmnopqrstuvwxyz" not in payload["exception"]
    assert "[redacted]" in payload["exception"]
