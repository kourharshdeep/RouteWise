"""Journey planning API routes."""
from __future__ import annotations

from typing import List
from fastapi import APIRouter

from src.api.schemas.journey import (
    JourneyPlace,
    JourneyPlanRequest,
    JourneyPlanResponse,
)
from src.services.journey_service import journey_service

router = APIRouter(prefix="/v1/journey", tags=["Journey Planning"])


@router.get("/places", response_model=List[JourneyPlace])
def get_places() -> List[JourneyPlace]:
    """Returns the verified landmark locations along the NH-44 Ramban–Banihal corridor."""
    return journey_service.get_corridor_places()


@router.post("/plan", response_model=JourneyPlanResponse)
def plan_journey(req: JourneyPlanRequest) -> JourneyPlanResponse:
    """Plans a corridor journey with segment hazard profiling and vehicle advisories."""
    return journey_service.plan_journey(req)
