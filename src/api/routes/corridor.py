"""Corridor topology and highway geometry endpoints."""
from __future__ import annotations

from fastapi import APIRouter

from src.api.schemas.corridor import CorridorGeoJSONResponse
from src.services.corridor_service import corridor_service

router = APIRouter(prefix="/v1/corridor", tags=["Corridor Topology"])


@router.get("/segments", response_model=CorridorGeoJSONResponse)
def get_corridor_segments() -> CorridorGeoJSONResponse:
    """Returns the 151 highway segments of the Ramban–Banihal corridor as GeoJSON LineStrings."""
    return corridor_service.get_corridor_geojson()
