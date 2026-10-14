"""Corridor topology and GeoJSON response schemas."""
from __future__ import annotations

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class SegmentProperties(BaseModel):
    """Terrain and highway attributes for a segment."""

    segment_id: str
    length_m: float
    slope: float
    elevation_m: float
    highway: str = "trunk"
    ref: str = "NH44"
    is_primary_road: int = 1


class GeoJSONGeometry(BaseModel):
    """LineString coordinate geometry in WGS84 [lon, lat]."""

    type: str = "LineString"
    coordinates: List[List[float]]


class SegmentFeature(BaseModel):
    """GeoJSON Feature representing one highway segment."""

    type: str = "Feature"
    id: str
    geometry: GeoJSONGeometry
    properties: SegmentProperties


class SegmentWeatherDetail(BaseModel):
    """Daily meteorological inputs for segment on requested date."""

    date: str
    precip_mm: float
    precip_3d_mm: float
    precip_7d_mm: float
    temp_mean_c: float
    temp_min_c: float
    snowfall_mm_we: float
    snow_depth_m: float
    data_source: str = "ERA5-Land reanalysis via Copernicus CDS (Historical Retrospective)"


class SegmentFeatureDetailResponse(BaseModel):
    """Segment attributes, genuine input features, and linked field reports for risk drawer."""

    segment_id: str
    date: str
    length_m: float
    slope_deg: float
    slope_pct: float
    elevation_m: float
    highway: str
    weather: Optional[SegmentWeatherDetail] = None
    reports: List[Dict[str, Any]] = []
    disclaimer: str = (
        "Input features for this segment represent physical terrain attributes and historical "
        "ERA5-Land meteorological conditions. They are input observations, not a model explanation."
    )


class AlongRouteServiceItem(BaseModel):
    """Emergency or transit facility located along the corridor."""

    id: str
    name: str
    type: str  # hospital, police, fuel, mechanic
    lat: float
    lon: float
    source: str
    verified: bool
    last_checked: str
    notes: Optional[str] = None


class OfficialAdvisoriesResponse(BaseModel):
    """Verified official traffic police advisory contacts and channels."""

    authority: str
    disclaimer: str
    last_verified: str
    verification_status: str
    official_channels: List[Dict[str, Any]]
    control_units: List[Dict[str, Any]]


class CorridorGeoJSONResponse(BaseModel):
    """GeoJSON FeatureCollection representing the Ramban–Banihal corridor."""

    type: str = "FeatureCollection"
    features: List[SegmentFeature]
    corridor_name: str = "NH-44 Ramban–Banihal Pilot Stretch"
    total_segments: int = 151
    crs: str = "EPSG:4326"
