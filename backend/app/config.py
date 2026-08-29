from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


def _env_file_paths() -> tuple[str, ...]:
    """Load `.env` from cwd or repo root when present; never require it to start."""
    candidates = [Path(".env"), Path("../.env")]
    return tuple(str(path) for path in candidates if path.is_file())


class Settings(BaseSettings):
    """Process configuration from the environment. No secrets are required to boot yet."""

    model_config = SettingsConfigDict(
        env_file=_env_file_paths(),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    app_env: Literal["development", "production"] = "development"
    log_level: str = "INFO"
    cors_origins: str = "http://localhost:3000"
    api_host: str = "127.0.0.1"
    api_port: int = Field(default=8000, ge=1, le=65535)
    openai_api_key: str = ""
    max_upload_bytes: int = Field(default=10 * 1024 * 1024, gt=0)
    max_inflight_jobs: int = Field(default=4, ge=1, le=32)
    api_store_dir: str = ""
    service_name: str = "forecastwize"
    service_version: str = "0.1.0"

    def api_store_path(self) -> Path:
        if self.api_store_dir.strip():
            return Path(self.api_store_dir).expanduser().resolve()
        backend_root = Path(__file__).resolve().parents[1]
        repo_root = backend_root.parent
        if (repo_root / "evaluation").is_dir():
            return repo_root / "data" / "api"
        return backend_root / "data" / "api"

    @field_validator("log_level")
    @classmethod
    def normalize_log_level(cls, value: str) -> str:
        level = value.upper()
        allowed = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        if level not in allowed:
            msg = f"LOG_LEVEL must be one of {sorted(allowed)}"
            raise ValueError(msg)
        return level

    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]

    def has_llm_key(self) -> bool:
        return bool(self.openai_api_key.strip())


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
