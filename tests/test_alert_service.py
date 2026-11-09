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


def test_replay_scenario_storm_progression(auth_tokens, set_live_mode):
    """Executes multi-day storm demo steps, verifying alerts fire, routes turn to HOLD, and recovery clears."""
    set_live_mode("replay")
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


def test_stale_high_risk_alert_retention():
    """Proves a stale high_risk alert remains ACTIVE with is_stale_context=True."""
    alert_service.clear_all_alerts()
    t0 = datetime(2026, 11, 1, 10, 0, 0, tzinfo=timezone.utc)
    sid = "seg_test_stale_01"

    # 1. Fresh state with high risk: creates active alert
    fresh_payload = [{"segment_id": sid, "risk_score": 0.82, "is_stale": False, "operational_status": "OPEN"}]
    alert_service.sync_alerts_from_live_state(live_risk_payload=fresh_payload, active_events=[], now_dt=t0)

    alerts_t0 = alert_service.get_active_alerts()
    assert len(alerts_t0) == 1
    assert alerts_t0[0]["alert_type"] == "high_risk"
    assert alerts_t0[0]["status"] == "active"
    assert alerts_t0[0]["is_stale_context"] is False

    # 2. At T+25h: risk data is stale
    t_stale = t0 + timedelta(hours=25)
    stale_payload = [{"segment_id": sid, "risk_score": 0.82, "is_stale": True, "operational_status": "OPEN"}]
    alert_service.sync_alerts_from_live_state(live_risk_payload=stale_payload, active_events=[], now_dt=t_stale)

    alerts_stale = alert_service.get_active_alerts()
    high_alerts = [a for a in alerts_stale if a["alert_type"] == "high_risk"]
    assert len(high_alerts) == 1
    assert high_alerts[0]["status"] == "active"
    assert high_alerts[0]["is_stale_context"] is True


def test_closure_alert_unaffected_by_risk_staleness():
    """Closure alerts come from hazard events, not model; unchanged by risk staleness (is_stale_context=False)."""
    alert_service.clear_all_alerts()
    t0 = datetime(2026, 11, 1, 10, 0, 0, tzinfo=timezone.utc)
    sid = "seg_test_closure_01"

    ev = {
        "id": "ev_01",
        "segment_id": sid,
        "hazard_type": "landslide",
        "severity": "critical",
        "status": "active",
        "expires_at": (t0 + timedelta(hours=5)).isoformat(),
    }
    # Evaluated with stale risk data
    stale_payload = [{"segment_id": sid, "risk_score": None, "is_stale": True, "operational_status": "CLOSED"}]
    alert_service.sync_alerts_from_live_state(live_risk_payload=stale_payload, active_events=[ev], now_dt=t0)

    alerts = alert_service.get_active_alerts()
    closure_alerts = [a for a in alerts if a["alert_type"] == "closure"]
    assert len(closure_alerts) == 1
    assert closure_alerts[0]["status"] == "active"
    assert closure_alerts[0]["is_stale_context"] is False


def test_stale_alert_text_immutability():
    """Database title and description remain byte-for-byte unchanged after stale evaluations."""
    alert_service.clear_all_alerts()
    t0 = datetime(2026, 11, 1, 10, 0, 0, tzinfo=timezone.utc)
    sid = "seg_test_immut_01"

    fresh_payload = [{"segment_id": sid, "risk_score": 0.75, "is_stale": False, "operational_status": "OPEN"}]
    alert_service.sync_alerts_from_live_state(live_risk_payload=fresh_payload, active_events=[], now_dt=t0)

    with alert_service._get_connection() as conn:
        row_before = dict(conn.execute("SELECT * FROM alert WHERE segment_id = ?", (sid,)).fetchone())

    # Stale evaluation
    stale_payload = [{"segment_id": sid, "risk_score": 0.75, "is_stale": True, "operational_status": "OPEN"}]
    alert_service.sync_alerts_from_live_state(live_risk_payload=stale_payload, active_events=[], now_dt=t0 + timedelta(hours=25))

    with alert_service._get_connection() as conn:
        row_after = dict(conn.execute("SELECT * FROM alert WHERE segment_id = ?", (sid,)).fetchone())

    assert row_after["title_en"] == row_before["title_en"]
    assert row_after["title_hi"] == row_before["title_hi"]
    assert row_after["message_en"] == row_before["message_en"]
    assert row_after["message_hi"] == row_before["message_hi"]
    assert "last known, data stale" not in row_after["title_en"]
    assert row_after["is_stale_context"] == 1


def test_stale_alert_recovery():
    """Repeated stale evaluations do not duplicate alerts or mutate text; fresh low-risk resolves alert."""
    alert_service.clear_all_alerts()
    t0 = datetime(2026, 11, 1, 10, 0, 0, tzinfo=timezone.utc)
    sid = "seg_test_recov_01"

    # 1. Fresh high-risk
    alert_service.sync_alerts_from_live_state(
        live_risk_payload=[{"segment_id": sid, "risk_score": 0.85, "is_stale": False, "operational_status": "OPEN"}],
        active_events=[],
        now_dt=t0,
    )
    with alert_service._get_connection() as conn:
        orig_title = conn.execute("SELECT title_en FROM alert WHERE segment_id = ?", (sid,)).fetchone()["title_en"]

    # 2. Repeated stale evaluations (T+25h, T+26h, T+27h)
    for hr in (25, 26, 27):
        alert_service.sync_alerts_from_live_state(
            live_risk_payload=[{"segment_id": sid, "risk_score": 0.85, "is_stale": True, "operational_status": "OPEN"}],
            active_events=[],
            now_dt=t0 + timedelta(hours=hr),
        )

    alerts = alert_service.get_active_alerts()
    high_alerts = [a for a in alerts if a["alert_type"] == "high_risk"]
    assert len(high_alerts) == 1, "Repeated stale evaluations must not duplicate high_risk alerts"
    assert high_alerts[0]["title_en"] == orig_title, "Title must not be mutated"
    assert high_alerts[0]["is_stale_context"] is True

    # 3. Fresh low-risk arrives at T+48h: resolves alert
    alert_service.sync_alerts_from_live_state(
        live_risk_payload=[{"segment_id": sid, "risk_score": 0.05, "is_stale": False, "operational_status": "OPEN"}],
        active_events=[],
        now_dt=t0 + timedelta(hours=48),
    )
    alerts_after = alert_service.get_active_alerts()
    high_after = [a for a in alerts_after if a["alert_type"] == "high_risk"]
    assert len(high_after) == 0, "Fresh low risk data must resolve the high_risk alert"


def test_closure_alert_resolves_only_when_event_closed():
    """Closure alerts stay active through risk staleness and resolve only when hazard event clears."""
    alert_service.clear_all_alerts()
    t0 = datetime(2026, 11, 1, 10, 0, 0, tzinfo=timezone.utc)
    sid = "seg_test_close_res_01"

    ev = {
        "id": "ev_close_01",
        "segment_id": sid,
        "hazard_type": "landslide",
        "severity": "critical",
        "status": "active",
        "expires_at": (t0 + timedelta(hours=10)).isoformat(),
    }
    # Active hazard with stale telemetry
    alert_service.sync_alerts_from_live_state(
        live_risk_payload=[{"segment_id": sid, "risk_score": None, "is_stale": True, "operational_status": "CLOSED"}],
        active_events=[ev],
        now_dt=t0,
    )
    alerts = alert_service.get_active_alerts()
    assert any(a["alert_type"] == "closure" and a["status"] == "active" for a in alerts)

    # Hazard cleared
    alert_service.sync_alerts_from_live_state(
        live_risk_payload=[{"segment_id": sid, "risk_score": 0.1, "is_stale": False, "operational_status": "OPEN"}],
        active_events=[],
        now_dt=t0 + timedelta(hours=1),
    )
    alerts_cleared = alert_service.get_active_alerts()
    assert not any(a["alert_type"] == "closure" for a in alerts_cleared)


def test_alert_api_response_and_legacy_schema_migration(tmp_path):
    """Verifies that an old-schema DB without is_stale_context is migrated safely and loads via API."""
    import sqlite3
    import contextlib
    from src.services.weather.storage import WeatherStorage
    from src.services.alert_service import AlertService

    old_db_path = tmp_path / "legacy_alerts.db"
    with contextlib.closing(sqlite3.connect(str(old_db_path))) as conn:
        conn.execute(
            """
            CREATE TABLE alert (
                id TEXT PRIMARY KEY,
                segment_id TEXT NOT NULL,
                alert_type TEXT NOT NULL,
                severity TEXT NOT NULL,
                title_en TEXT NOT NULL,
                title_hi TEXT NOT NULL,
                message_en TEXT NOT NULL,
                message_hi TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'active',
                is_simulated INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                acknowledged_at TEXT,
                acknowledged_by INTEGER,
                cleared_at TEXT
            );
            """
        )
        conn.execute(
            """
            INSERT INTO alert (id, segment_id, alert_type, severity, title_en, title_hi, message_en, message_hi, status, is_simulated, created_at)
            VALUES ('old_alert_01', 'seg_old_01', 'high_risk', 'warning', 'Legacy Title', '?????? ??????', 'Legacy Msg', '?????? ?????', 'active', 0, '2026-10-01T00:00:00Z');
            """
        )
        conn.commit()

    storage = WeatherStorage(db_path=old_db_path)
    legacy_service = AlertService(storage=storage)
    # Run migration
    legacy_service.init_db()

    # Verify column exists and old row has is_stale_context=0
    with contextlib.closing(sqlite3.connect(str(old_db_path))) as conn:
        cols = [info[1] for info in conn.execute("PRAGMA table_info(alert)").fetchall()]
        assert "is_stale_context" in cols
        row = conn.execute("SELECT is_stale_context FROM alert WHERE id = 'old_alert_01'").fetchone()
        assert row[0] == 0

    # Verify reading via service formats is_stale_context as False
    active = legacy_service.get_active_alerts()
    assert len(active) == 1
    assert active[0]["is_stale_context"] is False

    # Second init_db is idempotent
    legacy_service.init_db()
