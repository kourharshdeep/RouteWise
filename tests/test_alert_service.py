"""Tests for Alert and Monitoring Service (Step 7).

Verifies:
1. Alert creation and bilingual notification templates (English + Hindi unreviewed).
2. De-duplication logic: no duplicate active alerts for (segment_id, alert_type).
3. 1-hour cooldown: alert cannot be re-created within 3600s of clearance.
4. Auto-clearance when risk drops (<0.35) or closure is resolved.
5. Role-based access control matrix (read for all; patrol/admin for acknowledge and clear).
6. In-app delivery channel boundary enforcement.
7. Multi-day storm replay demonstration scenario execution.
"""
from __future__ import annotations

import pytest
from datetime import datetime, timedelta, timezone
from fastapi.testclient import TestClient

from src.api.app import app
from src.services.alert_service import alert_service
from src.services.auth_service import auth_service
from src.services.live_broadcast_service import live_broadcaster

client = TestClient(app)


@pytest.fixture(autouse=True)
def clean_alert_db():
    """Ensures a clean alert database for each test."""
    alert_service.clear_all_alerts()
    yield
    alert_service.clear_all_alerts()


@pytest.fixture
def auth_tokens():
    """Generates authentic bearer tokens for admin, patrol, and commuter test users."""
    with auth_service._get_connection() as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO users (id, email, name, password_hash, salt, role, preferred_vehicle, created_at, is_simulated)
            VALUES (99, 'admin@routewise.ai', 'System Admin', 'hash', 'salt', 'admin', 'Car', '2026-10-01T00:00:00Z', 1)
            """
        )
        conn.commit()

    admin_token = auth_service.create_token(user_id=99, email="admin@routewise.ai", role="admin")
    user_token = auth_service.create_token(user_id=1, email="demo@routewise.ai", role="user")
    patrol_token = auth_service.create_token(user_id=2, email="patrol@routewise.ai", role="patrol")

    return {
        "admin": f"Bearer {admin_token}",
        "patrol": f"Bearer {patrol_token}",
        "user": f"Bearer {user_token}",
    }


def test_alert_creation_and_bilingual_templates():
    """Tests creation of bilingual corridor alerts and in-app metadata."""
    alert_service.init_db()
    seg_id = "test_seg_bilingual_01"

    alert = alert_service.create_alert(
        segment_id=seg_id,
        alert_type="closure",
        severity="critical",
    )
    assert alert is not None
    assert alert["segment_id"] == seg_id
    assert alert["alert_type"] == "closure"
    assert alert["severity"] == "critical"
    assert "Corridor Segment Closure" in alert["title_en"]
    assert "गलियारा खंड" in alert["title_hi"]
    assert alert["delivery_channel"] == "in_app_only"
    assert "In-App Advisory Only" in alert["delivery_notice"]


def test_alert_deduplication_and_cooldown():
    """Verifies that duplicate active alerts are rejected, and 1-hour cooldown is enforced."""
    alert_service.init_db()
    seg_id = "test_seg_dedup_01"

    now = datetime(2026, 11, 3, 12, 0, 0, tzinfo=timezone.utc)

    # 1. Create first alert
    a1 = alert_service.create_alert(
        segment_id=seg_id,
        alert_type="high_risk",
        now_dt=now,
    )
    assert a1 is not None

    # 2. Attempt duplicate while active -> should return None (deduplicated)
    a2 = alert_service.create_alert(
        segment_id=seg_id,
        alert_type="high_risk",
        now_dt=now + timedelta(minutes=5),
    )
    assert a2 is None

    # 3. Clear alert at T+10 min
    alert_service.clear_alert(a1["id"], now_dt=now + timedelta(minutes=10))

    # 4. Attempt re-creation at T+20 min (within 1-hour cooldown) -> should return None
    a3 = alert_service.create_alert(
        segment_id=seg_id,
        alert_type="high_risk",
        now_dt=now + timedelta(minutes=20),
    )
    assert a3 is None

    # 5. Attempt re-creation at T+75 min (past 1-hour cooldown from cleared_at at T+10 min) -> should succeed
    a4 = alert_service.create_alert(
        segment_id=seg_id,
        alert_type="high_risk",
        now_dt=now + timedelta(minutes=75),
    )
    assert a4 is not None
    assert a4["id"] != a1["id"]


def test_auto_clear_when_risk_drops_or_hazard_clears():
    """Verifies that alerts automatically clear when road state clears."""
    alert_service.init_db()
    seg_id = "test_seg_autoclear_01"
    now = datetime(2026, 11, 3, 14, 0, 0, tzinfo=timezone.utc)

    # Create active closure and high_risk alerts
    alert_service.create_alert(seg_id, "closure", now_dt=now)
    alert_service.create_alert(seg_id, "high_risk", now_dt=now)

    # Simulate corridor sync where segment has dropped to Low risk (0.05) and OPEN
    mock_risk = {
        "segments": [
            {
                "segment_id": seg_id,
                "risk_score": 0.05,
                "risk_tier": "Low",
                "operational_status": "OPEN",
                "has_simulated_event": False,
            }
        ]
    }
    mock_events = []

    res = alert_service.sync_alerts_from_live_state(
        live_risk_payload=mock_risk,
        active_events=mock_events,
        now_dt=now + timedelta(minutes=2),
    )
    assert res["cleared"] >= 2

    # Verify both are now cleared
    active = alert_service.get_active_alerts()
    active_ids = [a["segment_id"] for a in active if a["segment_id"] == seg_id]
    assert len(active_ids) == 0


def test_role_matrix_acknowledgement_and_clearing(auth_tokens):
    """Enforces RBAC: public read; patrol/admin only for acknowledge and clear."""
    alert_service.init_db()
    seg_id = "test_seg_rbac_01"

    alert = alert_service.create_alert(segment_id=seg_id, alert_type="hazard_disruption")
    alert_id = alert["id"]

    # 1. Public read for active alerts (no token required)
    res_pub = client.get("/api/v1/alerts/active")
    assert res_pub.status_code == 200
    data = res_pub.json()
    assert data["delivery_channel"] == "in_app_only"
    assert any(a["id"] == alert_id for a in data["alerts"])

    # 2. Acknowledge with no token -> 401
    res_unauth = client.post(f"/api/v1/alerts/{alert_id}/acknowledge")
    assert res_unauth.status_code == 401

    # 3. Acknowledge with Commuter token -> 403 Forbidden
    res_commuter = client.post(
        f"/api/v1/alerts/{alert_id}/acknowledge",
        headers={"Authorization": auth_tokens["user"]},
    )
    assert res_commuter.status_code == 403

    # 4. Acknowledge with Patrol token -> 200 OK
    res_patrol = client.post(
        f"/api/v1/alerts/{alert_id}/acknowledge",
        headers={"Authorization": auth_tokens["patrol"]},
    )
    assert res_patrol.status_code == 200
    assert res_patrol.json()["status"] == "acknowledged"

    # 5. Clear with Commuter token -> 403 Forbidden
    res_clr_commuter = client.post(
        f"/api/v1/alerts/{alert_id}/clear",
        headers={"Authorization": auth_tokens["user"]},
    )
    assert res_clr_commuter.status_code == 403

    # 6. Clear with Admin token -> 200 OK
    res_clr_admin = client.post(
        f"/api/v1/alerts/{alert_id}/clear",
        headers={"Authorization": auth_tokens["admin"]},
    )
    assert res_clr_admin.status_code == 200
    assert res_clr_admin.json()["status"] == "cleared"


def test_in_app_boundary_disclaimer():
    """Guarantees every alert payload includes the in-app only constraint."""
    res = client.get("/api/v1/alerts/active")
    assert res.status_code == 200
    body = res.json()
    assert body["delivery_channel"] == "in_app_only"
    assert "In-App Advisory Only" in body["delivery_notice"]
    assert "No SMS" in body["delivery_notice"]


def test_replay_scenario_storm_progression(auth_tokens):
    """Executes multi-day storm demo steps, verifying alerts fire, routes turn to HOLD, and recovery clears."""
    # Step 0: Normal Baseline (2023-07-06)
    res_step0 = client.post(
        "/api/v1/alerts/scenario/step",
        headers={"Authorization": auth_tokens["admin"]},
        json={"step_index": 0},
    )
    assert res_step0.status_code == 200
    d0 = res_step0.json()
    assert d0["step"] == 0
    assert d0["phase"] == "Baseline Clear"
    assert d0["route_recommendation"] in ("PROCEED", "PROCEED_WITH_CAUTION", "DELAY")

    # Step 3: Peak Cloudburst & Cafeteria Morh Landslide (2023-07-09)
    res_step3 = client.post(
        "/api/v1/alerts/scenario/step",
        headers={"Authorization": auth_tokens["admin"]},
        json={"step_index": 3},
    )
    assert res_step3.status_code == 200
    d3 = res_step3.json()
    assert d3["step"] == 3
    assert d3["phase"] == "Peak Cloudburst & Obstruction"
    assert d3["route_recommendation"] == "HOLD"
    assert d3["active_alerts_count"] > 0
    assert any(a["alert_type"] == "closure" for a in d3["alerts"])

    # Step 4: Post-Storm Recovery (2023-07-10)
    res_step4 = client.post(
        "/api/v1/alerts/scenario/step",
        headers={"Authorization": auth_tokens["admin"]},
        json={"step_index": 4},
    )
    assert res_step4.status_code == 200
    d4 = res_step4.json()
    assert d4["step"] == 4
    assert d4["phase"] == "Post-Storm Clearance"
    assert d4["route_recommendation"] != "HOLD"
