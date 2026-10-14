"""Corridor topology, segment features, and along-route infrastructure endpoints."""
from __future__ import annotations

from typing import Any, Dict, List, Optional
from fastapi import APIRouter, Depends, Query

from src.api.dependencies import security
from src.api.schemas.auth import UserProfile
from src.api.schemas.corridor import (
    AlongRouteServiceItem,
    CorridorGeoJSONResponse,
    OfficialAdvisoriesResponse,
    SegmentFeatureDetailResponse,
)
from src.services.auth_service import auth_service
from src.services.corridor_service import corridor_service

router = APIRouter(prefix="/v1/corridor", tags=["Corridor Topology"])


def get_optional_user(
    credentials=Depends(security),
) -> Optional[UserProfile]:
    """Helper that extracts user profile if token provided, else None."""
    if not credentials or not credentials.credentials:
        return None
    try:
        payload = auth_service.verify_token(credentials.credentials)
        user_id = int(payload.get("sub", 0))
        return auth_service.get_user_by_id(user_id)
    except Exception:
        return None


@router.get("/segments", response_model=CorridorGeoJSONResponse)
def get_corridor_segments() -> CorridorGeoJSONResponse:
    """Returns the 151 highway segments of the Ramban–Banihal corridor as GeoJSON LineStrings."""
    return corridor_service.get_corridor_geojson()


@router.get("/segments/{segment_id}/features", response_model=SegmentFeatureDetailResponse)
def get_segment_features(
    segment_id: str,
    date: str = Query(..., description="Observation date (YYYY-MM-DD)"),
    current_user: Optional[UserProfile] = Depends(get_optional_user),
) -> SegmentFeatureDetailResponse:
    """Returns terrain metrics, ERA5-Land weather inputs, and linked reports for a segment on an observation date."""
    return corridor_service.get_segment_features(segment_id, date, current_user)


@router.get("/services", response_model=List[AlongRouteServiceItem])
def get_along_route_services() -> List[AlongRouteServiceItem]:
    """Returns verified and static emergency, health, and transit services along the NH-44 corridor."""
    return corridor_service.get_along_route_services()


@router.get("/advisories", response_model=OfficialAdvisoriesResponse)
def get_official_advisories() -> OfficialAdvisoriesResponse:
    """Returns officially published J&K Traffic Police channels, emergency phone numbers, and control units."""
    return corridor_service.get_official_advisories()


@router.get("/weather")
def get_corridor_weather(
    date: str = Query(..., description="Observation date (YYYY-MM-DD)"),
) -> Dict[str, Any]:
    """Returns historical daily weather observations across all corridor segments for map overlay."""
    return corridor_service.get_corridor_weather(date)
