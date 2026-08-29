from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_serializer


class HealthResponse(BaseModel):
    """Public health payload. Field names are the API contract for the frontend client."""

    model_config = ConfigDict(extra="forbid")

    status: Literal["ok"]
    service: str
    version: str
    environment: Literal["development", "production"]
    timestamp: datetime
    llm_configured: bool = Field(
        description=(
            "Whether an LLM API key is present. False is expected until agents are implemented."
        )
    )

    @field_serializer("timestamp")
    def serialize_timestamp(self, value: datetime) -> str:
        aware = value if value.tzinfo is not None else value.replace(tzinfo=UTC)
        return aware.astimezone(UTC).isoformat().replace("+00:00", "Z")


class PublicErrorResponse(BaseModel):
    """Client-facing error. No stack traces."""

    model_config = ConfigDict(extra="forbid")

    error_code: str
    message: str
    request_id: str | None = None
