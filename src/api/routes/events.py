"""Hazard Event and Operator Simulation API Routes.

Honest Framing:
- Simulation endpoints are restricted strictly to administrators (HTTP 403 otherwise).
- All simulated incidents are permanently badged as 'SIMULATED' (is_simulated=True).
- Simulated events are contained exclusively within the runtime database and never
  contaminate historical training data.
- Events act as an overlay: they never change the underlying ST-GNN model weights or scores.
"""
from __future__ import annotations

from typing import List, Optional
from fastapi import APIRouter, Depends, Query, status

from src.api.dependencies import require_admin
from src.api.schemas.auth import UserProfile
from src.api.schemas.events import (
    ClearSimulatedResponse,
    HazardEventItem,
    SimulateEventRequest,
)
from src.services.hazard_event_service import hazard_event_service

router = APIRouter(prefix="/v1/events", tags=["Hazard Events"])


@router.post(
    "/simulate",
    response_model=HazardEventItem,
    status_code=status.HTTP_201_CREATED,
    summary="Operator hazard simulation (Admin only)",
)
def simulate_hazard_event(
    req: SimulateEventRequest,
    current_user: UserProfile = Depends(require_admin),
) -> HazardEventItem:
    """Injects an operator-simulated hazard event onto an NH-44 segment.
    
    Restricted to Administrator role. Always flagged is_simulated=True and badged 'SIMULATED'.
    """
    event = hazard_event_service.simulate_event(
        preset=req.preset,
        segment_id=req.segment_id,
        severity=req.severity,
        duration_hours=req.duration_hours,
        user_id=current_user.id,
    )
    return HazardEventItem(**event)


@router.post(
    "/simulate/clear",
    response_model=ClearSimulatedResponse,
    summary="Clear all active simulated hazard events (Admin only)",
)
def clear_simulated_events(
    current_user: UserProfile = Depends(require_admin),
) -> ClearSimulatedResponse:
    """One-action teardown closing all active operator-simulated hazard events."""
    cleared = hazard_event_service.clear_all_simulated_events(user_id=current_user.id)
    return ClearSimulatedResponse(cleared_count=cleared)


@router.get(
    "/active",
    response_model=List[HazardEventItem],
    summary="List active hazard events (Public)",
)
def get_active_events(
    segment_id: Optional[str] = Query(None, description="Optional filter by road segment ID")
) -> List[HazardEventItem]:
    """Returns currently active verified and simulated hazard events. Public read access."""
    events = hazard_event_service.get_active_events(segment_id=segment_id)
    return [HazardEventItem(**e) for e in events]
