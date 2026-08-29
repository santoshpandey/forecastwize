from __future__ import annotations

import logging
from pathlib import Path

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from pydantic import ValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.api.datasets import router as datasets_router
from app.api.errors import (
    ApiError,
    api_error_handler,
    http_exception_handler,
    unhandled_exception_handler,
    validation_exception_handler,
)
from app.api.evaluations import router as evaluations_router
from app.api.forecasts import router as forecasts_router
from app.api.request_ids import request_id_middleware
from app.api.runs import router as runs_router
from app.api.store import FileStore
from app.config import get_settings
from app.health import router as health_router
from app.structured_logging import configure_logging

logger = logging.getLogger(__name__)


def create_app(*, store_dir: Path | None = None) -> FastAPI:
    settings = get_settings()
    configure_logging(settings)

    application = FastAPI(
        title="ForecastWize API",
        version=settings.service_version,
        description=(
            "HTTP adapter for ForecastWize. Handlers validate input, call domain "
            "or graph functions, and return typed models. Numerical forecasts come "
            "from deterministic Python, not from this layer."
        ),
        docs_url="/docs" if settings.app_env == "development" else None,
        redoc_url=None,
        openapi_url="/openapi.json" if settings.app_env == "development" else None,
    )

    origins = settings.cors_origin_list()
    application.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=False,
        allow_methods=["GET", "HEAD", "OPTIONS", "POST"],
        allow_headers=["Content-Type", "Accept", "X-Request-ID"],
    )
    application.middleware("http")(request_id_middleware)

    application.add_exception_handler(ApiError, api_error_handler)
    application.add_exception_handler(RequestValidationError, validation_exception_handler)
    application.add_exception_handler(ValidationError, validation_exception_handler)
    application.add_exception_handler(StarletteHTTPException, http_exception_handler)
    application.add_exception_handler(Exception, unhandled_exception_handler)

    root = store_dir if store_dir is not None else settings.api_store_path()
    application.state.store = FileStore(root)

    application.include_router(health_router)
    application.include_router(datasets_router)
    application.include_router(forecasts_router)
    application.include_router(runs_router)
    application.include_router(evaluations_router)
    logger.info(
        "app_created",
        extra={
            "event": "app_created",
            "environment": settings.app_env,
            "cors_origin_count": len(origins),
        },
    )
    return application


app = create_app()
