from __future__ import annotations

import pytest
from app.config import Settings
from pydantic import ValidationError


def test_invalid_log_level_is_rejected() -> None:
    with pytest.raises(ValidationError):
        Settings(log_level="NOT_A_LEVEL")


def test_cors_origins_parsed_as_allowlist() -> None:
    settings = Settings(cors_origins="http://localhost:3000, http://127.0.0.1:3000")
    assert settings.cors_origin_list() == [
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ]


def test_max_inflight_jobs_must_be_at_least_one() -> None:
    with pytest.raises(ValidationError):
        Settings(max_inflight_jobs=0)
