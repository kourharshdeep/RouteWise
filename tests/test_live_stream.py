"""Tests for RouteWise Server-Sent Events (SSE) live updates and broadcaster.

Verifies:
- Subscription lifecycle and event broadcast delivery
- Initial 'status' and 'risk_update' frames on connect
- Real-time event forwarding (risk_update, event_update, alert, route_update)
- Periodic heartbeats every 20s (tested via parameterized interval)
- Connection cleanup on client disconnect
"""
from __future__ import annotations

import asyncio
import json
import httpx
import pytest
from fastapi.testclient import TestClient

from src.api.app import app
from src.services.live_broadcast_service import live_broadcaster, LiveBroadcaster
from src.services.live_risk_service import LiveRiskService
from src.services.weather.replay import ReplayProvider
from src.services.weather.storage import WeatherStorage
from pathlib import Path


def test_broadcaster_lifecycle_and_delivery():
    """Verifies subscribe, broadcast_sync, and unsubscribe mechanics."""
    b = LiveBroadcaster()
    assert b.subscriber_count == 0

    q = b.subscribe()
    assert b.subscriber_count == 1

    test_data = {"segment_id": "test_seg_01", "score": 0.42}
    b.broadcast_sync("risk_update", test_data)

    assert not q.empty()
    frame = q.get_nowait()
    assert frame["event"] == "risk_update"
    assert frame["data"] == test_data
    assert "timestamp" in frame

    b.unsubscribe(q)
    assert b.subscriber_count == 0


def test_sse_initial_frames():
    """Verifies that opening /api/v1/live/stream yields initial status and risk frames."""
    client = TestClient(app)
    # Using max_events=2 to receive the 2 initial frames and close cleanly
    response = client.get("/api/v1/live/stream?max_events=2")
    assert response.status_code == 200
    assert "text/event-stream" in response.headers["content-type"]

    lines = response.text.strip().split("\n")
    events_received = [l.split(":", 1)[1].strip() for l in lines if l.startswith("event:")]

    assert "status" in events_received
    assert "risk_update" in events_received


def test_sse_receives_broadcast():
    """Verifies that events dispatched via live_broadcaster are streamed into the SSE output."""
    async def _run():
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            # Enqueue a broadcast event right before opening stream
            payload = {"action": "simulated_test", "active_count": 3}

            # We use max_events=3 so it emits status, risk_update, and the broadcast event
            # Schedule broadcast after brief delay
            async def _dispatch_delayed():
                await asyncio.sleep(0.05)
                live_broadcaster.broadcast_sync("event_update", payload)

            task = asyncio.create_task(_dispatch_delayed())
            response = await client.get("/api/v1/live/stream?max_events=3&heartbeat_interval=5.0")
            await task

            assert response.status_code == 200
            assert "event: event_update" in response.text
            assert "simulated_test" in response.text

    asyncio.run(_run())


def test_sse_heartbeat_emission():
    """Verifies that if no event occurs within heartbeat_interval, a heartbeat is emitted."""
    client = TestClient(app)
    # With max_events=3 and heartbeat_interval=0.1, after 2 initial frames, a heartbeat fires!
    response = client.get("/api/v1/live/stream?max_events=3&heartbeat_interval=0.1")
    assert response.status_code == 200
    assert "event: heartbeat" in response.text
    assert '"status": "alive"' in response.text


def test_compute_live_risk_emits_valid_sse_event(tmp_path: Path):
    """Regression test for Fix 1: compute_live_risk must emit a valid risk_update frame to SSE subscribers."""
    test_db = tmp_path / "test_live_broadcast.db"
    storage = WeatherStorage(db_path=test_db)
    storage.init_db()
    service = LiveRiskService(storage=storage)
    service.init_db()

    provider = ReplayProvider(csv_path="data/weather_daily_by_segment.csv")
    df_7days = provider.fetch(start_date="2024-07-01", end_date="2024-07-07")
    storage.upsert_observations(df_7days)

    q = live_broadcaster.subscribe()
    try:
        while not q.empty():
            q.get_nowait()

        records = service.compute_live_risk(as_of="2024-07-07")
        assert len(records) == 151

        events = []
        while not q.empty():
            events.append(q.get_nowait())

        risk_updates = [e for e in events if e.get("event") == "risk_update"]
        assert len(risk_updates) == 1, f"Expected 1 risk_update event, received {len(risk_updates)}"

        payload = risk_updates[0]["data"]
        assert payload.get("as_of") == "2024-07-07"
        assert payload.get("computed_at") is not None
        assert payload.get("segments_count") == len(records)
    finally:
        live_broadcaster.unsubscribe(q)


def test_failing_broadcaster_does_not_break_compute_live_risk(tmp_path: Path, monkeypatch):
    """Verifies that if broadcaster raises an exception, live_risk rows are still committed successfully."""
    test_db = tmp_path / "test_broadcaster_fail.db"
    storage = WeatherStorage(db_path=test_db)
    storage.init_db()
    service = LiveRiskService(storage=storage)
    service.init_db()

    provider = ReplayProvider(csv_path="data/weather_daily_by_segment.csv")
    df_7days = provider.fetch(start_date="2024-07-01", end_date="2024-07-07")
    storage.upsert_observations(df_7days)

    def mock_broadcast_fail(*args, **kwargs):
        raise RuntimeError("Simulated network/queue transport disaster")

    monkeypatch.setattr(live_broadcaster, "broadcast_sync", mock_broadcast_fail)

    records = service.compute_live_risk(as_of="2024-07-07")
    assert len(records) == 151

    with service._get_connection() as conn:
        count = conn.execute("SELECT COUNT(*) FROM live_risk WHERE as_of = '2024-07-07'").fetchone()[0]
    assert count == 151

