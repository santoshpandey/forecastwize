"""Named baseline forecast HTTP adapter. No agent graph. No metric invention."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends

from app.api.deps import get_store
from app.api.errors import ApiError
from app.api.ids import new_prefixed_id, require_resource_id
from app.api.schemas import ForecastCreateRequest, ForecastResponse
from app.api.series_io import load_dataset_frame, resolve_frequency, series_columns
from app.api.store import FileStore
from app.forecasting.base import ForecastInterfaceError
from app.services.forecast_service import run_baseline_forecast
from app.time_utils import utc_now

router = APIRouter(tags=["forecasts"])
logger = logging.getLogger(__name__)


@router.post("/forecasts", response_model=ForecastResponse, status_code=201)
def create_forecast(
    body: ForecastCreateRequest,
    store: FileStore = Depends(get_store),
) -> ForecastResponse:
    require_resource_id(body.dataset_id)
    dataset, frame = load_dataset_frame(store, body.dataset_id)
    frequency = resolve_frequency(dataset, body.frequency)
    timestamps, values, _events, _context = series_columns(frame)
    try:
        result = run_baseline_forecast(
            timestamps,
            values,
            frequency=frequency,
            horizon=body.horizon,
            model_id=body.model_id,
            coverage=body.coverage,
            seed=body.seed,
            seasonal_period=body.seasonal_period,
        )
    except ForecastInterfaceError as exc:
        raise ApiError(422, "forecast_error", str(exc)) from exc

    record = ForecastResponse(
        id=new_prefixed_id("fc"),
        dataset_id=body.dataset_id,
        created_at=utc_now(),
        model_id=body.model_id,
        result=result,
    )
    store.put_forecast(record)
    logger.info(
        "forecast_created",
        extra={
            "event": "forecast_created",
            "forecast_id": record.id,
            "dataset_id": record.dataset_id,
            "model_id": record.model_id,
            "horizon": body.horizon,
            "frequency": frequency,
            "seed": body.seed,
        },
    )
    return record


@router.get("/forecasts/{forecast_id}", response_model=ForecastResponse)
def get_forecast(forecast_id: str, store: FileStore = Depends(get_store)) -> ForecastResponse:
    require_resource_id(forecast_id)
    record = store.get_forecast(forecast_id)
    logger.info(
        "forecast_fetched",
        extra={"event": "forecast_fetched", "forecast_id": forecast_id},
    )
    return record
