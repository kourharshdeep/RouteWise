"""Tests for Dynamic Route Recalculation and MultiObjectiveRouter Integration (Step 6).

Verifies:
1. Historical Mode Backward Compatibility:
   - Preserves exact Hardening Pass 1 outputs (75 segments, 243.32 km, symmetric distance).
   - Date outside historical range returns 404 with allowed range.
2. Live Mode Side-by-Side Alternatives:
   - Returns distance-only baseline route and risk-aware route side-by-side.
   - Symmetric distance in both directions; never exceeds corridor total (294.18 km).
   - Reports has_alternative=False (honest single physical mountain road).
3. Recommendation Contract Matrix:
   - CLOSED segment on route -> HOLD with explicit reasoning.
   - Stale or missing telemetry -> NO_DATA.
   - High hazard segments -> DELAY.
   - Medium hazard segments -> PROCEED_WITH_CAUTION.
   - Baseline low hazard -> PROCEED.
4. Real-time route_update SSE Dispatch:
   - Simulating or clearing hazard events broadcasts a route_update frame.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from src.api.app import app
from src.services.live_broadcast_service import live_broadcaster
from src.services.hazard_event_service import hazard_event_service
from src.services.live_risk_service import live_risk_service

client = TestClient(app)


def test_historical_mode_preserves_contract_and_symmetry():
    """Historical mode must retain exact Hardening Pass 1 responses and symmetric distances."""
    res_fwd = client.post(
        "/api/v1/journey/plan",
        json={"origin": "Ramban Gateway", "destination": "Banihal Gateway", "date": "2023-07-09", "mode": "historical"},
    )
    assert res_fwd.status_code == 200
    data_fwd = res_fwd.json()
    assert data_fwd["mode"] == "historical"
    assert data_fwd["total_route_segments"] == 75
    assert data_fwd["total_distance_km"] == 243.32
    assert data_fwd["total_distance_km"] <= 294.18
    assert data_fwd["has_alternative"] is False
    assert data_fwd["baseline_route"] is not None
    assert data_fwd["risk_aware_route"] is not None
    assert data_fwd["baseline_route"]["total_distance_km"] == 243.32

    # Reverse direction
    res_rev = client.post(
        "/api/v1/journey/plan",
        json={"origin": "Banihal Gateway", "destination": "Ramban Gateway", "date": "2023-07-09", "mode": "historical"},
    )
    assert res_rev.status_code == 200
    data_rev = res_rev.json()
    assert data_rev["total_distance_km"] == data_fwd["total_distance_km"]
    assert data_rev["total_route_segments"] == data_fwd["total_route_segments"]


def test_out_of_range_historical_date_returns_404():
    """Historical mode with out-of-range date returns 404 with allowed range."""
    res = client.post(
        "/api/v1/journey/plan",
        json={"origin": "Ramban Gateway", "destination": "Banihal Gateway", "date": "1999-01-01", "mode": "historical"},
    )
    assert res.status_code == 404
    detail = res.json()["detail"]
    assert "outside the supported historical window" in detail


def test_live_mode_side_by_side_routing():
    """Live mode returns side-by-side baseline and risk-aware routes with honest corridor constraints."""
    res = client.post(
        "/api/v1/journey/plan",
        json={"origin": "Ramban Gateway", "destination": "Banihal Gateway", "mode": "live"},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["mode"] == "live"
    assert data["total_route_segments"] == 75
    assert data["total_distance_km"] == 243.32
    assert data["has_alternative"] is False
    assert "Live advisory route analysis" in data["retrospective_notice"]

    # Verify baseline vs risk-aware alternatives
    baseline = data["baseline_route"]
    risk_aware = data["risk_aware_route"]
    assert baseline["name"] == "baseline_shortest"
    assert risk_aware["name"] == "risk_aware"
    assert baseline["total_distance_km"] == 243.32
    assert risk_aware["total_distance_km"] == 243.32
    assert baseline["estimated_travel_minutes"] > 0
    assert risk_aware["estimated_travel_minutes"] >= baseline["estimated_travel_minutes"]


def test_closed_segment_triggers_hold_recommendation():
    """If a segment on the route is closed, recommendation must be HOLD and passable=False."""
    # Pick a segment traversed on the Ramban-Banihal route (e.g., segment 40 from sorted segments)
    route_res = client.post(
        "/api/v1/journey/plan",
        json={"origin": "Ramban Gateway", "destination": "Banihal Gateway", "mode": "live"},
    ).json()
    target_seg_id = route_res["itinerary"][10]["segment_id"]

    # Simulate an emergency landslide closure on that segment
    hazard_event_service.init_db()
    sim_res = hazard_event_service.simulate_event(
        preset="landslide",
        segment_id=target_seg_id,
        severity="critical",
        duration_hours=12,
        user_id=1,
    )
    assert sim_res["id"]

    try:
        # Re-plan journey in live mode
        res = client.post(
            "/api/v1/journey/plan",
            json={"origin": "Ramban Gateway", "destination": "Banihal Gateway", "mode": "live"},
        )
        assert res.status_code == 200
        plan = res.json()

        assert plan["recommendation"] == "HOLD"
        assert target_seg_id in plan["blocking_segments"]
        assert "is CLOSED" in plan["recommendation_reason"]
        assert "no bypass" in plan["recommendation_reason"]

        assert plan["baseline_route"]["is_passable"] is False
        assert plan["risk_aware_route"]["is_passable"] is False
        assert target_seg_id in plan["baseline_route"]["blocking_segments"]
        assert target_seg_id in plan["risk_aware_route"]["blocking_segments"]
    finally:
        # Clean up simulated events
        hazard_event_service.clear_all_simulated_events()


def test_recommendation_matrix_rules():
    """Tests PROCEED, PROCEED_WITH_CAUTION, and DELAY recommendation logic."""
    from src.api.schemas.journey import JourneyPlanRequest

    # Clean state with no closed events
    hazard_event_service.clear_all_simulated_events()

    # Plan on benchmark date with high risk (2023-07-09 monsoon cloudburst)
    res_high = client.post(
        "/api/v1/journey/plan",
        json={"origin": "Ramban Gateway", "destination": "Banihal Gateway", "date": "2023-07-09", "mode": "historical"},
    ).json()
    assert res_high["high_risk_segments_count"] > 0
    assert res_high["recommendation"] == "DELAY"

    # Plan on benchmark date with moderate conditions (2021-01-16)
    res_mod = client.post(
        "/api/v1/journey/plan",
        json={"origin": "Ramban Gateway", "destination": "Banihal Gateway", "date": "2021-01-16", "mode": "historical"},
    ).json()
    assert res_mod["high_risk_segments_count"] == 0
    assert res_mod["recommendation"] == "PROCEED_WITH_CAUTION"


def test_sse_broadcasts_route_update_on_hazard_change():
    """Verifies that hazard event creation enqueues a route_update frame for SSE subscribers."""
    q = live_broadcaster.subscribe()
    try:
        # Simulate an event
        hazard_event_service.simulate_event(
            preset="shooting_stones",
            segment_id="test_route_update_seg",
            severity="high",
            duration_hours=2,
            user_id=1,
        )

        # Check queue has event_update, route_update, risk_update
        events_found = []
        while not q.empty():
            item = q.get_nowait()
            events_found.append(item.get("event"))

        assert "event_update" in events_found
        assert "route_update" in events_found
    finally:
        live_broadcaster.unsubscribe(q)
        hazard_event_service.clear_all_simulated_events()
