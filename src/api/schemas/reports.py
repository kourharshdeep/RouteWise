"""Field report request and response schemas."""
from __future__ import annotations

from enum import Enum
from typing import List, Optional
from pydantic import BaseModel, Field


class ReportCategory(str, Enum):
    LANDSLIDE = "landslide"
    SHOOTING_STONES = "shooting_stones"
    FLOODING = "flooding"
    ROAD_DAMAGE = "road_damage"
    SINGLE_LANE_OR_OBSTRUCTION = "single_lane_or_obstruction"
    SNOW_OR_ICE = "snow_or_ice"
    OTHER = "other"


class ReportStatus(str, Enum):
    SUBMITTED = "submitted"
    VERIFIED = "verified"
    ASSIGNED = "assigned"
    RESOLVED = "resolved"
    REJECTED = "rejected"


class ReportStatusUpdateRequest(BaseModel):
    """Payload to transition report status."""

    status: ReportStatus
    note: Optional[str] = Field(default=None, description="Mandatory note for rejection or reopening")


class ReportAssignRequest(BaseModel):
    """Payload to assign a report to a patrol officer."""

    assigned_to: int = Field(..., description="User ID of the patrol officer")
    note: Optional[str] = Field(default=None, description="Optional assignment notes or instructions")


class ReportStatusHistoryItem(BaseModel):
    """Single status transition audit record."""

    id: int
    report_id: str
    from_status: Optional[str] = None
    to_status: str
    actor_id: int
    actor_name: Optional[str] = None
    actor_role: str
    note: Optional[str] = None
    timestamp: str


class ReportResponse(BaseModel):
    """Detailed field report with full audit history and assignee info."""

    id: str
    client_uuid: str
    reporter_id: int
    reporter_name: Optional[str] = None
    category: str
    description: Optional[str] = None
    latitude: float
    longitude: float
    nearest_segment_id: Optional[str] = None
    nearest_segment_distance_m: Optional[float] = None
    has_photo: bool = False
    photo_url: Optional[str] = None
    status: str
    assigned_to: Optional[int] = None
    assigned_to_name: Optional[str] = None
    client_created_at: Optional[str] = None
    created_at: str
    updated_at: str
    is_simulated: bool = False
    history: List[ReportStatusHistoryItem] = []


class PublicReportItem(BaseModel):
    """Redacted report representation for public/guest map display."""

    id: str
    category: str
    description: Optional[str] = None
    latitude: float
    longitude: float
    nearest_segment_id: Optional[str] = None
    has_photo: bool = False
    photo_url: Optional[str] = None
    status: str
    created_at: str
    is_simulated: bool = False


class ReportListResponse(BaseModel):
    """Paginated list of reports for patrol operations dashboard."""

    items: List[ReportResponse]
    total: int
    limit: int
    offset: int


class ReportSummaryStats(BaseModel):
    """Summary counts by status for operations overview."""

    total: int
    submitted: int
    verified: int
    assigned: int
    resolved: int
    rejected: int
