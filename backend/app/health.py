from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, Request

from app.config import Settings, get_settings
from app.schemas import HealthResponse
from app.time_utils import utc_now

router = APIRouter(tags=["health"])
logger = logging.getLogger(__name__)


@router.get("/health", response_model=HealthResponse)
def get_health(request: Request, settings: Settings = Depends(get_settings)) -> HealthResponse:
    logger.info(
        "health_checked",
        extra={
            "event": "health_checked",
            "path": str(request.url.path),
            "environment": settings.app_env,
        },
    )
    return HealthResponse(
        status="ok",
        service=settings.service_name,
        version=settings.service_version,
        environment=settings.app_env,
        timestamp=utc_now(),
        llm_configured=settings.has_llm_key(),
    )
