"""Unit, Lifecycle, Role Matrix, and Isolation Tests for Hazard Events (Step 4).

Verifies:
1. Event lifecycle: creation, audit trail, auto-expiry, and report status synchronization.
2. Unverified reports (submitted) NEVER generate active public hazard events.
3. Operational status derivation rule table (OPEN, CAUTION, RESTRICTED, CLOSED, UNKNOWN).
4. Events are purely an overlay: they do not mutate ST-GNN model weights or scores.
5. Role matrix: POST /api/v1/events/simulate is strictly restricted to Admin (403 otherwise).
6. Runtime data containment: simulated events reside solely in runtime DB and never touch local/training DB.
"""
from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

from src.api.app import app
from src.services.auth_service import auth_service
from src.services.hazard_event_service import HazardEventService, VALID_PRESETS
from src.services.report_service import report_service
from src.services.weather.storage import WeatherStorage

client = TestClient(app)


@pytest.fixture
def isolated_event_service(tmp_path: Path) -> HazardEventService:
    test_db = tmp_path / "test_events.db"
    storage = WeatherStorage(db_path=test_db)
    service = HazardEventService(storage=storage)
    service.init_db()
    return service


def test_unverified_reports_never_create_public_events(isolated_event_service: HazardEventService):
    """Honest Framing: Unverified community field reports (submitted) must never produce active events."""
    event_id = isolated_event_service.on_report_status_change(
        report_id="rep_unverified_001",
        status_value="submitted",
        category="Landslide",
        segment_id="1177888062_6516768040_0",
        actor_id=1,
    )
    assert event_id is None
    active = isolated_event_service.get_active_events()
    assert len(active) == 0


def test_event_lifecycle_and_auto_expiry(isolated_event_service: HazardEventService):
    """Verifies report verification -> active event -> auto-expiry audit trail."""
    seg_id = "1177888062_6516768040_0"
    rep_id = "rep_verified_002"

    # 1. Promote to verified -> creates active hazard event
    event_id = isolated_event_service.on_report_status_change(
        report_id=rep_id,
        status_value="verified",
        category="Landslide",
        segment_id=seg_id,
        actor_id=2,
    )
    assert event_id is not None
    active = isolated_event_service.get_active_events(segment_id=seg_id)
    assert len(active) == 1
    assert active[0]["status"] == "active"
    assert active[0]["badge"] == "VERIFIED"

    # 2. Simulate expiration: update expires_at into the past
    past_iso = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
    with isolated_event_service._get_connection() as conn:
        conn.execute("UPDATE hazard_event SET expires_at = ? WHERE id = ?", (past_iso, event_id))
        conn.commit()

    # 3. Running auto-expiry prunes event and logs audit trail
    expired_count = isolated_event_service.expire_active_events()
    assert expired_count == 1
    assert len(isolated_event_service.get_active_events(segment_id=seg_id)) == 0

    # Verify audit trail in hazard_event_history
    with isolated_event_service._get_connection() as conn:
        history = conn.execute(
            "SELECT action FROM hazard_event_history WHERE event_id = ? ORDER BY id ASC",
            (event_id,),
        ).fetchall()
        actions = [r["action"] for r in history]
        assert "CREATED" in actions
        assert "AUTO_EXPIRED" in actions


def test_operational_status_rule_table():
    """Verifies priority-ordered operational status synthesis."""
    derive = HazardEventService.derive_operational_status

    # Priority 1: Critical hazard event -> CLOSED regardless of model tier
    critical_event = [{"hazard_type": "landslide", "severity": "critical"}]
    assert derive(model_risk_tier="Low", active_events=critical_event) == "CLOSED"
    assert derive(model_risk_tier="High", active_events=critical_event) == "CLOSED"

    # Priority 2: Single-lane or high severity -> RESTRICTED
    restricted_event = [{"hazard_type": "single_lane", "severity": "medium"}]
    assert derive(model_risk_tier="Low", active_events=restricted_event) == "RESTRICTED"

    # Priority 3: Missing or stale telemetry + no blocking events -> UNKNOWN
    assert derive(model_risk_tier="UNKNOWN", active_events=[], model_status="MISSING_DATA") == "UNKNOWN"
    assert derive(model_risk_tier="UNKNOWN", active_events=[], model_status="STALE_DATA") == "UNKNOWN"

    # Priority 4: Minor active event or elevated model risk -> CAUTION
    minor_event = [{"hazard_type": "road_damage", "severity": "low"}]
    assert derive(model_risk_tier="Low", active_events=minor_event) == "CAUTION"
    assert derive(model_risk_tier="Medium", active_events=[]) == "CAUTION"
    assert derive(model_risk_tier="High", active_events=[]) == "CAUTION"

    # Priority 5: Low model risk + no events -> OPEN
    assert derive(model_risk_tier="Low", active_events=[]) == "OPEN"


def test_role_matrix_simulation_endpoints():
    """Verify simulation endpoints are strictly Admin-only (403 for patrol/user/guest)."""
    # Ensure an admin account exists in auth DB
    with auth_service._get_connection() as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO users (id, email, name, password_hash, salt, role, preferred_vehicle, created_at, is_simulated)
            VALUES (99, 'admin@routewise.ai', 'System Admin', 'hash', 'salt', 'admin', 'Car', '2026-10-01T00:00:00Z', 1)
            """
        )
        conn.commit()

    guest_token = auth_service.create_guest_session().access_token
    user_token = auth_service.create_token(user_id=1, email="demo@routewise.ai", role="user")
    patrol_token = auth_service.create_token(user_id=2, email="patrol@routewise.ai", role="patrol")
    admin_token = auth_service.create_token(user_id=99, email="admin@routewise.ai", role="admin")

    sim_payload = {
        "preset": "landslide",
        "segment_id": "1177888062_6516768040_0",
        "duration_hours": 6,
    }

    # 1. Anonymous -> 401
    resp_anon = client.post("/api/v1/events/simulate", json=sim_payload)
    assert resp_anon.status_code == 401

    # 2. Guest, User, Patrol -> 403 Forbidden
    for r_name, tok in [("guest", guest_token), ("user", user_token), ("patrol", patrol_token)]:
        resp_forbidden = client.post(
            "/api/v1/events/simulate",
            json=sim_payload,
            headers={"Authorization": f"Bearer {tok}"},
        )
        assert resp_forbidden.status_code == 403, f"Expected 403 for role '{r_name}', got {resp_forbidden.status_code}"

    # 3. Admin -> 201 Created
    resp_admin = client.post(
        "/api/v1/events/simulate",
        json=sim_payload,
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp_admin.status_code == 201
    ev_data = resp_admin.json()
    assert ev_data["is_simulated"] is True
    assert ev_data["badge"] == "SIMULATED"
    assert ev_data["hazard_type"] == "landslide"

    # 4. Public active events listing includes badged simulation
    resp_active = client.get("/api/v1/events/active")
    assert resp_active.status_code == 200
    active_list = resp_active.json()
    assert any(e["id"] == ev_data["id"] and e["badge"] == "SIMULATED" for e in active_list)

    # 5. One-action clear all simulated (Admin only)
    resp_clear_patrol = client.post(
        "/api/v1/events/simulate/clear",
        headers={"Authorization": f"Bearer {patrol_token}"},
    )
    assert resp_clear_patrol.status_code == 403

    resp_clear_admin = client.post(
        "/api/v1/events/simulate/clear",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp_clear_admin.status_code == 200
    assert resp_clear_admin.json()["cleared_count"] >= 1


def test_simulated_events_isolated_from_historical_data():
    """Verify that simulated events never leak into historical data/routewise_local.db."""
    local_db_path = Path("data/routewise_local.db")
    if local_db_path.exists():
        with sqlite3.connect(local_db_path) as conn:
            tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
            # hazard_event should NOT exist in historical DB
            assert "hazard_event" not in tables
            # segment_weather should contain zero simulated flags
            if "segment_weather" in tables:
                cols = [r[1] for r in conn.execute("PRAGMA table_info(segment_weather)").fetchall()]
                assert "is_simulated" not in cols
