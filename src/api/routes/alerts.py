"""Alert and Real-Time Monitoring API Routes.

Honest Framing & Role-Based Access:
- All users (including public/guest) can view active alerts and alert history.
- Alert acknowledgement and manual clearing are restricted strictly to Patrol officers and Administrators.
- All endpoints communicate in-app delivery channel constraints.
"""
from __future__ import annotations

from typing import List, Optional
from fastapi import APIRouter, Depends, Query, status

from src.api.dependencies import get_current_user, require_authenticated, require_patrol
from src.api.schemas.alerts import (
    AcknowledgeAlertResponse,
    AlertItem,
    AlertListResponse,
    ClearAlertResponse,
    ScenarioStepRequest,
    ScenarioStepResponse,
)
from src.api.schemas.auth import UserProfile
from src.services.alert_service import alert_service

router = APIRouter(prefix="/v1/alerts", tags=["Alerts & Monitoring"])


@router.get(
    "/active",
    response_model=AlertListResponse,
    summary="Get active and acknowledged corridor alerts (Public)",
)
def get_active_alerts(
    limit: int = Query(100, ge=1, le=500),
) -> AlertListResponse:
    """Returns active and acknowledged corridor hazard alerts.
    
    Advisory alerts are delivered strictly in-app. Missing or stale data produces
    UNKNOWN status rather than low risk.
    """
    alerts = alert_service.get_active_alerts(limit=limit)
    active_count = sum(1 for a in alerts if a["status"] == "active")
    ack_count = sum(1 for a in alerts if a["status"] == "acknowledged")

    return AlertListResponse(
        alerts=[AlertItem(**a) for a in alerts],
        total=len(alerts),
        active_count=active_count,
        acknowledged_count=ack_count,
    )


@router.get(
    "/history",
    response_model=AlertListResponse,
    summary="Get alert history audit log (Public)",
)
def get_alert_history(
    limit: int = Query(100, ge=1, le=500),
) -> AlertListResponse:
    """Returns chronological alert history including cleared alerts."""
    alerts = alert_service.get_alert_history(limit=limit)
    active_count = sum(1 for a in alerts if a["status"] == "active")
    ack_count = sum(1 for a in alerts if a["status"] == "acknowledged")

    return AlertListResponse(
        alerts=[AlertItem(**a) for a in alerts],
        total=len(alerts),
        active_count=active_count,
        acknowledged_count=ack_count,
    )


@router.post(
    "/{alert_id}/acknowledge",
    response_model=AcknowledgeAlertResponse,
    summary="Acknowledge alert (Patrol or Admin only)",
)
def acknowledge_alert(
    alert_id: str,
    current_user: UserProfile = Depends(require_patrol),
) -> AcknowledgeAlertResponse:
    """Marks an active alert as acknowledged by a patrol officer."""
    res = alert_service.acknowledge_alert(alert_id=alert_id, user_id=current_user.id)
    return AcknowledgeAlertResponse(**res)


@router.post(
    "/{alert_id}/clear",
    response_model=ClearAlertResponse,
    summary="Manually clear alert (Patrol or Admin only)",
)
def clear_alert(
    alert_id: str,
    current_user: UserProfile = Depends(require_patrol),
) -> ClearAlertResponse:
    """Manually clears an active or acknowledged alert."""
    res = alert_service.clear_alert(alert_id=alert_id, user_id=current_user.id)
    return ClearAlertResponse(**res)


@router.post(
    "/scenario/step",
    response_model=ScenarioStepResponse,
    summary="Execute multi-day storm demo replay step",
)
def step_scenario(
    req: ScenarioStepRequest,
    current_user: UserProfile = Depends(get_current_user),
) -> ScenarioStepResponse:
    """Steps through the July 2023 monsoon storm demonstration scenario.
    
    Steps:
    0: Baseline Clear (2023-07-06)
    1: Storm Approach (2023-07-07)
    2: Severe Rainfall (2023-07-08)
    3: Peak Cloudburst & Cafeteria Morh Landslide (2023-07-09)
    4: Post-Storm Recovery & Clearance (2023-07-10)
    """
    res = alert_service.step_replay_scenario(step_index=req.step_index, user_id=current_user.id)
    return ScenarioStepResponse(**res)
