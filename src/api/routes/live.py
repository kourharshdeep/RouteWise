"""Real-Time Intelligence & Live Risk Endpoints.

Honest Framing:
- All endpoints are public read (accessible to guests and registered users alike).
- Outputs are explicitly tagged as 'experimental' with honest distribution shift warnings.
- No reporter-identifying information is returned.
"""
from __future__ import annotations

from typing import Optional
from fastapi import APIRouter, Query

from src.api.schemas.live import (
    LiveRiskChangesResponse,
    LiveRiskResponse,
    LiveStatusResponse,
)
from src.services.live_risk_service import live_risk_service

router = APIRouter(prefix="/v1/live", tags=["Real-Time Intelligence"])


@router.get("/status", response_model=LiveStatusResponse)
def get_live_status() -> LiveStatusResponse:
    """Returns operational live mode status, provider health, data freshness, and validation metrics."""
    return LiveStatusResponse(**live_risk_service.get_live_status())


@router.get("/risk", response_model=LiveRiskResponse)
def get_live_risk() -> LiveRiskResponse:
    """Returns latest live ST-GNN disruption risk predictions for the 151 corridor segments."""
    return LiveRiskResponse(**live_risk_service.get_latest_live_risk())


@router.get("/changes", response_model=LiveRiskChangesResponse)
def get_live_changes(
    since: Optional[str] = Query(
        None,
        description="ISO 8601 UTC timestamp to retrieve incremental changes after (e.g. '2026-11-03T12:00:00Z')",
    )
) -> LiveRiskChangesResponse:
    """Returns risk predictions that were computed or modified after the given timestamp."""
    return LiveRiskChangesResponse(**live_risk_service.get_risk_changes(since=since))
