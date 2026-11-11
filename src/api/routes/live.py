"""Real-Time Intelligence & Live Risk Endpoints.

Honest Framing:
- All endpoints are public read (accessible to guests and registered users alike).
- Outputs are explicitly tagged as 'experimental' with honest distribution shift warnings.
- No reporter-identifying information is returned.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
import json
import logging
from typing import Optional
from fastapi import APIRouter, Query, Request
from fastapi.responses import StreamingResponse

from src.api.schemas.live import (
    LiveRiskChangesResponse,
    LiveRiskResponse,
    LiveStatusResponse,
)
from src.services.live_risk_service import live_risk_service
from src.services.live_broadcast_service import live_broadcaster

logger = logging.getLogger("routewise.live_routes")

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


@router.get("/stream")
async def get_live_stream(
    request: Request,
    heartbeat_interval: float = Query(20.0, description="Heartbeat interval in seconds (default 20.0s)"),
    max_events: Optional[int] = Query(None, description="Optional cap on frames to emit before closing (useful for tests)"),
):
    """Server-Sent Events (SSE) live updates stream.

    Yields real-time events for connected clients:
    - initial: 'status' and 'risk_update'
    - ongoing: 'risk_update', 'event_update', 'alert', 'route_update', 'status'
    - keep-alive: 'heartbeat' every 20 seconds
    """
    queue = live_broadcaster.subscribe()

    async def event_generator():
        emitted = 0
        try:
            # 1. Emit initial state immediately upon connection
            try:
                status_data = live_risk_service.get_live_status()
                yield f"event: status\ndata: {json.dumps(status_data)}\n\n"
                emitted += 1
            except Exception as e:
                logger.debug("Error generating initial status frame: %s", e)

            if max_events is not None and emitted >= max_events:
                return

            try:
                risk_data = live_risk_service.get_latest_live_risk()
                yield f"event: risk_update\ndata: {json.dumps(risk_data)}\n\n"
                emitted += 1
            except Exception as e:
                logger.debug("Error generating initial risk frame: %s", e)

            if max_events is not None and emitted >= max_events:
                return

            # 2. Main event loop
            while True:
                if max_events is not None and emitted >= max_events:
                    break
                try:
                    msg = await asyncio.wait_for(queue.get(), timeout=heartbeat_interval)
                    event_type = msg.get("event", "message")
                    data_str = json.dumps(msg.get("data", {}))
                    yield f"event: {event_type}\ndata: {data_str}\n\n"
                    emitted += 1
                except asyncio.TimeoutError:
                    hb = {
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                        "status": "alive",
                    }
                    yield f"event: heartbeat\ndata: {json.dumps(hb)}\n\n"
                    emitted += 1
        except (asyncio.CancelledError, GeneratorExit):
            pass
        finally:
            live_broadcaster.unsubscribe(queue)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
