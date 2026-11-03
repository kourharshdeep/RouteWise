"""Alert and Notification Pydantic Schemas.

Honest Framing & In-App Boundary:
- RouteWise alerts are delivered EXCLUSIVELY in-app via the dashboard UI.
- RouteWise does NOT integrate with SMS gateways, cellular broadcasts, or push notification daemons.
- All alert models include mandatory delivery_channel='in_app_only' metadata.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


IN_APP_DELIVERY_NOTICE = (
    "In-App Advisory Only: RouteWise alerts are delivered exclusively via the web interface. "
    "No SMS, push notifications, or cellular broadcasts are emitted."
)


class AlertItem(BaseModel):
    """Corridor alert item with bilingual notification strings and audit trail."""
    id: str
    segment_id: str
    alert_type: str = Field(..., description="Alert classification: high_risk | closure | hazard_disruption | weather_warning")
    severity: str = Field(..., description="Severity tier: critical | warning | advisory | info")
    title_en: str
    title_hi: str
    message_en: str
    message_hi: str
    status: str = Field("active", description="Lifecycle state: active | acknowledged | cleared")
    is_simulated: bool = Field(False, description="Whether alert originated from an operator simulated hazard")
    created_at: str
    acknowledged_at: Optional[str] = None
    acknowledged_by: Optional[int] = None
    cleared_at: Optional[str] = None
    delivery_channel: str = Field("in_app_only", description="Constrained delivery boundary")
    delivery_notice: str = Field(IN_APP_DELIVERY_NOTICE, description="Honest delivery channel disclaimer")


class AlertListResponse(BaseModel):
    """Response containing list of active or recent corridor alerts."""
    alerts: List[AlertItem]
    total: int
    active_count: int
    acknowledged_count: int
    delivery_channel: str = "in_app_only"
    delivery_notice: str = IN_APP_DELIVERY_NOTICE


class AcknowledgeAlertResponse(BaseModel):
    """Response returned upon patrol officer acknowledgement."""
    id: str
    status: str
    acknowledged_at: str
    acknowledged_by: int
    note: str = "Alert acknowledged by patrol officer"


class ClearAlertResponse(BaseModel):
    """Response returned upon alert clearance."""
    id: str
    status: str
    cleared_at: str
    note: str = "Alert cleared"


class ScenarioStepRequest(BaseModel):
    """Request to step through the multi-day storm demonstration scenario."""
    step_index: int = Field(..., ge=0, le=4, description="Step index: 0 (Normal) to 4 (Recovery)")


class ScenarioStepResponse(BaseModel):
    """Summary of the applied multi-day storm demonstration step."""
    step: int
    date: str
    phase: str
    title: str
    description: str
    active_alerts_count: int
    alerts: List[AlertItem]
    corridor_operational_status: str
    route_recommendation: str
    route_recommendation_reason: str
    is_simulated: bool = True
    delivery_channel: str = "in_app_only"
