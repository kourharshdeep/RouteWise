"""Corridor topology and GeoJSON response schemas."""
from __future__ import annotations

from typing import Any, Dict, List
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


class CorridorGeoJSONResponse(BaseModel):
    """GeoJSON FeatureCollection representing the Ramban–Banihal corridor."""

    type: str = "FeatureCollection"
    features: List[SegmentFeature]
    corridor_name: str = "NH-44 Ramban–Banihal Pilot Stretch"
    total_segments: int = 151
    crs: str = "EPSG:4326"
