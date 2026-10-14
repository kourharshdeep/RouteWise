"""Journey planning and route intelligence schemas."""
from __future__ import annotations

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class JourneyPlace(BaseModel):
    """Corridor landmark location."""

    id: str
    name: str
    lat: float
    lon: float
    description: str


class JourneyPlanRequest(BaseModel):
    """Request payload for planning a journey across the corridor."""

    origin: str = Field(..., description="Origin landmark (e.g. 'Ramban', 'Banihal', 'Digdol')")
    destination: str = Field(..., description="Destination landmark (e.g. 'Banihal', 'Ramban')")
    date: str = Field(..., description="Journey date in YYYY-MM-DD format")
    departure_time: str = Field(default="08:00", description="Preferred departure time (HH:MM)")
    arrival_deadline: Optional[str] = Field(None, description="Optional target arrival deadline (HH:MM)")
    vehicle_type: str = Field(
        default="Car",
        description="Vehicle category: Car, Motorcycle, Bus, Truck, Other",
    )


class SegmentItineraryItem(BaseModel):
    """Details for a single segment traversed along the route."""

    segment_id: str
    sequence: int
    length_m: float
    slope: float
    elevation_m: float
    risk_score: Optional[float]
    risk_tier: str
    highway: str
    hazard_notes: Optional[str] = None


class VehicleAdvisory(BaseModel):
    """Vehicle-specific operational advisory."""

    vehicle_type: str
    speed_limit_kmh: float
    vulnerability_level: str  # Standard, High, Extreme
    operational_clearance: str  # Cleared, Caution, Restricted
    advisory_text: str
    model_applicability_note: str


class JourneyPlanResponse(BaseModel):
    """Comprehensive journey plan analysis response."""

    origin: str
    destination: str
    journey_date: str
    departure_time: str
    estimated_arrival_time: str
    arrival_deadline: Optional[str]
    deadline_status: Optional[str]  # "Achievable", "At Risk", "Exceeded"
    total_distance_km: float
    estimated_travel_minutes: int
    vehicle_advisory: VehicleAdvisory
    overall_route_risk: str  # "Low", "Medium", "High"
    max_risk_score: float
    average_risk_score: float
    total_route_segments: int
    high_risk_segments_count: int
    medium_risk_segments_count: int
    low_risk_segments_count: int
    bottlenecks: List[str]
    historical_disruptions_on_route: int
    retrospective_notice: str
    itinerary: List[SegmentItineraryItem]
