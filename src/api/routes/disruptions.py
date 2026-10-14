"""Historical disruption API routes."""
from __future__ import annotations

from typing import Optional
from fastapi import APIRouter, Query

from src.api.schemas.disruptions import DisruptionListResponse, DisruptionStats
from src.services.disruption_service import disruption_service

router = APIRouter(prefix="/v1/disruptions", tags=["Historical Disruptions"])


@router.get("", response_model=DisruptionListResponse)
def get_disruptions(
    year: Optional[int] = Query(None, description="Filter by year (e.g. 2023)"),
    disruption_type: Optional[str] = Query(None, description="Filter by type (landslide, snow, shooting_stones)"),
    closure: Optional[str] = Query(None, description="Filter by closure (full, partial)"),
    query: Optional[str] = Query(None, description="Search keyword in location description or notes"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
) -> DisruptionListResponse:
    """Returns verified historical disruption records from the NH-44 Ramban–Banihal corridor log."""
    return disruption_service.get_disruptions(
        year=year,
        disruption_type=disruption_type,
        closure=closure,
        query=query,
        page=page,
        page_size=page_size,
    )


@router.get("/stats", response_model=DisruptionStats)
def get_disruption_stats() -> DisruptionStats:
    """Returns aggregated frequency and hotspot statistics for historical disruptions."""
    return disruption_service.get_stats()
