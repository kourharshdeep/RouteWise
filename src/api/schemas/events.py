"""Pydantic schemas for Hazard Events and Simulation Endpoints."""
from __future__ import annotations

from typing import Optional
from pydantic import BaseModel, Field


class SimulateEventRequest(BaseModel):
    preset: str = Field(
        ...,
        description="Hazard preset: 'landslide' | 'shooting_stones' | 'snow_ice' | 'flooding' | 'road_damage' | 'single_lane'",
        examples=["landslide"],
    )
    segment_id: str = Field(..., description="NH-44 road segment ID to attach the simulated event to")
    severity: Optional[str] = Field(
        None,
        description="Optional severity override: 'low' | 'medium' | 'high' | 'critical'. Defaults to preset setting.",
    )
    duration_hours: Optional[int] = Field(
        12,
        ge=1,
        le=168,
        description="Operational duration in hours before automatic expiration (default: 12h, max: 168h)",
    )


class HazardEventItem(BaseModel):
    id: str
    segment_id: str
    hazard_type: str
    severity: str
    status: str
    origin: str
    is_simulated: bool
    badge: str = Field(..., description="'SIMULATED' for operator simulations, 'VERIFIED' for confirmed reports")
    source_report_id: Optional[str] = None
    starts_at: str
    expires_at: str
    created_by: Optional[int] = None
    created_at: str


class ClearSimulatedResponse(BaseModel):
    cleared_count: int
    status: str = "SUCCESS"
    message: str = "All active operator-simulated hazard events have been cleared."
