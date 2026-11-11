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
    date: Optional[str] = Field(None, description="Journey date in YYYY-MM-DD format (required for historical mode)")
    mode: str = Field(default="historical", description="Routing mode: 'historical' | 'live'")
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
    operational_status: Optional[str] = None


class VehicleAdvisory(BaseModel):
    """Vehicle-specific operational advisory."""

    vehicle_type: str
    speed_limit_kmh: float
    vulnerability_level: str  # Standard, High, Extreme
    operational_clearance: str  # Cleared, Caution, Restricted
    advisory_text: str
    model_applicability_note: str


class RouteAlternative(BaseModel):
    """Side-by-side alternative route evaluation (baseline distance vs risk-aware)."""

    name: str = Field(..., description="Route variant: 'baseline_shortest' | 'risk_aware'")
    total_distance_km: float = Field(..., description="Total route distance in kilometers")
    estimated_travel_minutes: int = Field(..., description="Estimated travel time in minutes")
    travel_time_disclaimer: str = Field(
        default="Estimated transit time calculated from assumed vehicle speeds and hazard buffers; not measured live telemetry."
    )
    overall_risk: str = Field(..., description="Overall route risk tier: Low | Medium | High | Unknown")
    max_risk_score: Optional[float] = Field(None, description="Maximum segment risk score")
    average_risk_score: Optional[float] = Field(None, description="Average segment risk score")
    high_risk_segments_count: int = Field(..., description="High risk segments count")
    medium_risk_segments_count: int = Field(..., description="Medium risk segments count")
    low_risk_segments_count: int = Field(..., description="Low risk segments count")
    unknown_segments_count: int = Field(default=0, description="Unknown segments count")
    blocking_segments: List[str] = Field(default_factory=list, description="Closed or impassable segment IDs")
    is_passable: bool = Field(True, description="False if blocked by closed segment")
    trade_off_explanation: str = Field(default="", description="Router pathfinding explanation")


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
    travel_time_disclaimer: str = Field(
        default="Estimated transit time calculated from assumed vehicle speeds and hazard buffers; not measured live telemetry."
    )
    vehicle_advisory: VehicleAdvisory
    overall_route_risk: str  # "Low", "Medium", "High", "Unknown"
    max_risk_score: Optional[float] = None
    average_risk_score: Optional[float] = None
    total_route_segments: int
    high_risk_segments_count: int
    medium_risk_segments_count: int
    low_risk_segments_count: int
    unknown_segments_count: int = 0
    is_incomplete_data: bool = False
    bottlenecks: List[str]
    historical_disruptions_on_route: int
    retrospective_notice: str
    itinerary: List[SegmentItineraryItem]
    # Step 6 Dynamic Routing & Recommendation Contract:
    mode: str = Field(default="historical", description="'historical' | 'live'")
    recommendation: str = Field(
        default="PROCEED",
        description="Operational advisory recommendation: PROCEED | PROCEED_WITH_CAUTION | DELAY | HOLD | NO_DATA",
    )
    recommendation_reason: str = Field(
        default="",
        description="Explicit operational explanation for recommendation",
    )
    blocking_segments: List[str] = Field(
        default_factory=list,
        description="Segments closed or blocked along route",
    )
    has_alternative: bool = Field(
        default=False,
        description="True only if an actual topological bypass exists in corridor graph",
    )
    baseline_route: Optional[RouteAlternative] = Field(
        default=None,
        description="Distance-only baseline calculation",
    )
    risk_aware_route: Optional[RouteAlternative] = Field(
        default=None,
        description="Multi-objective risk-penalized calculation",
    )
    requested_date: Optional[str] = Field(
        default=None,
        description="The original journey date requested by the client",
    )
    date_substituted: bool = Field(
        default=False,
        description="True if requested date was substituted with the latest available live risk date",
    )
    actual_date: Optional[str] = Field(
        default=None,
        description="The actual telemetry date used to evaluate the journey plan",
    )

    def model_dump(self, *args, **kwargs):
        d = super().model_dump(*args, **kwargs)
        if not self.date_substituted and self.requested_date is None and self.actual_date is None:
            d.pop("requested_date", None)
            d.pop("date_substituted", None)
            d.pop("actual_date", None)
        return d
