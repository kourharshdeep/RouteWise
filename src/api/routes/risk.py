"""Risk prediction endpoints."""
from __future__ import annotations

from fastapi import APIRouter, Query

from src.api.schemas.risk import AvailableDatesResponse, CorridorRiskResponse
from src.services.risk_service import risk_service

router = APIRouter(prefix="/v1/risk", tags=["Risk Forecasts"])


@router.get("", response_model=CorridorRiskResponse)
def get_corridor_risk(
    date: str = Query(
        ...,
        description="Observation date in YYYY-MM-DD format (e.g. '2023-07-09')",
        examples=["2023-07-09"],
    )
) -> CorridorRiskResponse:
    """Returns retrospective segment disruption risk estimates for the specified observation date."""
    return risk_service.get_risk_by_date(date)


@router.get("/dates", response_model=AvailableDatesResponse)
def get_available_dates() -> AvailableDatesResponse:
    """Returns the date range and total available dates in the precomputed historical cache."""
    return risk_service.get_available_dates()
