"""Historical disruption schemas."""
from __future__ import annotations

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class DisruptionItem(BaseModel):
    """Historical disruption record from NH-44 field log."""

    id: int
    date: str
    location_desc: str
    lat: float
    lon: float
    location_confidence: str
    disruption_type: str
    closure: str
    duration_hours: Optional[float]
    source_name: str
    source_url: Optional[str]
    notes: str
    segment_id: Optional[str]
    snap_dist_m: Optional[float]
    snap_ok: bool


class DisruptionStats(BaseModel):
    """Statistical summary of historical corridor disruptions."""

    total_events: int
    by_type: Dict[str, int]
    by_year: Dict[str, int]
    top_locations: List[Dict[str, Any]]


class DisruptionListResponse(BaseModel):
    """Paginated list of historical disruption records."""

    total: int
    page: int
    page_size: int
    events: List[DisruptionItem]
