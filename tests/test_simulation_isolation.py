"""Tests for Server-Side Simulation Isolation (Task 3b-3 Section B).

Invariants verified:
1. In 'live' mode: simulated hazard events and simulated alerts are completely excluded
   from all read paths (active events, active alerts, corridor status, journey planner).
2. In 'replay' mode: simulated hazard events and simulated alerts are included.
3. In 'off' mode: simulated hazard events and simulated alerts are excluded.
4. Real events (is_simulated=False) remain visible and operational across all modes.
5. API response schemas expose 'is_simulated: bool' and 'badge: str'.
6. Backward compatibility: tables lacking the is_simulated column load gracefully.
7. In-memory cache invalidation preserves mode isolation.
"""
from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

from src.api.app import app
from src.api.config import settings
from src.services.alert_service import AlertService, alert_service
from src.services.hazard_event_service import HazardEventService, hazard_event_service
from src.services.journey_service import JourneyPlanRequest, journey_service
from src.services.live_risk_service import LiveRiskService, live_risk_service
from src.services.weather.storage import WeatherStorage, weather_storage

client = TestClient(app)


def _seed_minimal_live_risk(db_path: Path, segment_ids: list[str], as_of: str = "2026-11-10") -> None:
    """Helper to seed minimal live_risk table entries for tests."""
    with sqlite3.connect(str(db_path)) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS live_risk (
                segment_id TEXT PRIMARY KEY,
                as_of TEXT NOT NULL,
                score REAL,
                tier TEXT NOT NULL,
                status TEXT NOT NULL,
                is_stale INTEGER NOT NULL DEFAULT 0,
                model_version TEXT NOT NULL,
                checkpoint_sha256 TEXT NOT NULL,
                weather_window_end TEXT NOT NULL,
                computed_at TEXT NOT NULL
            );
            """
        )
        records = [
            (
                sid,
                as_of,
                0.05,
                "Low",
                "OK",
                0,
                "1.0.0",
                "sha256",
                f"{as_of}T00:00:00Z",
                f"{as_of}T10:00:00Z",
            )
            for sid in segment_ids
        ]
        conn.executemany(
            """
            INSERT OR REPLACE INTO live_risk (
                segment_id, as_of, score, tier, status, is_stale,
                model_version, checkpoint_sha256, weather_window_end, computed_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            records,
        )
        conn.commit()


@pytest.fixture
def isolated_services(tmp_path, monkeypatch):
    """Provides isolated storage and services backed by a temporary database."""
    test_db = tmp_path / "test_sim_isolation.db"
    storage = WeatherStorage(db_path=str(test_db))
    monkeypatch.setattr(weather_storage, "db_path", test_db)

    hazard_svc = HazardEventService(storage=storage)
    alert_svc = AlertService(storage=storage)
    risk_svc = LiveRiskService(storage=storage)

    hazard_svc.init_db()
    alert_svc.init_db()
    risk_svc.init_db()

    hazard_event_service.reset_db_init()
    live_risk_service.reset_db_init()

    # Pre-seed live risk rows for all corridor segments
    all_segs = journey_service._sorted_segment_ids
    _seed_minimal_live_risk(test_db, all_segs)

    return {
        "db_path": test_db,
        "storage": storage,
        "hazard_svc": hazard_svc,
        "alert_svc": alert_svc,
        "risk_svc": risk_svc,
        "all_segs": all_segs,
    }


def test_simulated_event_and_alert_hidden_in_live_mode(isolated_services, set_live_mode):
    """In live mode, simulated events and alerts are filtered out from all reads."""
    set_live_mode("live")
    hazard_svc: HazardEventService = isolated_services["hazard_svc"]
    alert_svc: AlertService = isolated_services["alert_svc"]
    all_segs = isolated_services["all_segs"]
    target_seg = all_segs[10]

    # 1. Create a simulated landslide event
    sim_event = hazard_svc.simulate_event(
        preset="landslide",
        segment_id=target_seg,
        severity="critical",
        duration_hours=12,
        user_id=1,
    )
    assert sim_event["is_simulated"] is True
    assert sim_event["badge"] == "SIMULATED"

    # 2. Create a simulated alert
    sim_alert = alert_svc.create_alert(
        segment_id=target_seg,
        alert_type="closure",
        severity="critical",
        is_simulated=True,
    )
    assert sim_alert is not None
    assert sim_alert["is_simulated"] is True

    # In live mode: get_active_events() must exclude the simulated event
    active_events = hazard_svc.get_active_events()
    assert len(active_events) == 0
    assert not any(e["id"] == sim_event["id"] for e in active_events)

    # In live mode: get_active_alerts() must exclude the simulated alert
    active_alerts = alert_svc.get_active_alerts()
    assert len(active_alerts) == 0
    assert not any(a["id"] == sim_alert["id"] for a in active_alerts)

    # In live mode: get_active_events_by_segment_map must be empty for target_seg
    events_map = hazard_svc.get_active_events_by_segment_map()
    assert target_seg not in events_map or len(events_map[target_seg]) == 0


def test_simulated_event_and_alert_visible_in_replay_mode(isolated_services, set_live_mode):
    """In replay mode, simulated events and alerts are included in reads."""
    set_live_mode("replay")
    hazard_svc: HazardEventService = isolated_services["hazard_svc"]
    alert_svc: AlertService = isolated_services["alert_svc"]
    all_segs = isolated_services["all_segs"]
    target_seg = all_segs[15]

    sim_event = hazard_svc.simulate_event(
        preset="landslide",
        segment_id=target_seg,
        severity="critical",
        duration_hours=12,
        user_id=1,
    )
    sim_alert = alert_svc.create_alert(
        segment_id=target_seg,
        alert_type="closure",
        severity="critical",
        is_simulated=True,
    )

    # In replay mode: get_active_events() must include the simulated event
    active_events = hazard_svc.get_active_events()
    assert any(e["id"] == sim_event["id"] and e["is_simulated"] is True for e in active_events)

    # In replay mode: get_active_alerts() must include the simulated alert
    active_alerts = alert_svc.get_active_alerts()
    assert any(a["id"] == sim_alert["id"] and a["is_simulated"] is True for a in active_alerts)


def test_simulated_event_and_alert_hidden_in_off_mode(isolated_services, set_live_mode):
    """In off mode, simulated events and alerts are excluded."""
    set_live_mode("off")
    hazard_svc: HazardEventService = isolated_services["hazard_svc"]
    alert_svc: AlertService = isolated_services["alert_svc"]
    all_segs = isolated_services["all_segs"]
    target_seg = all_segs[20]

    sim_event = hazard_svc.simulate_event(
        preset="snow_ice",
        segment_id=target_seg,
        severity="high",
        duration_hours=12,
        user_id=1,
    )
    sim_alert = alert_svc.create_alert(
        segment_id=target_seg,
        alert_type="high_risk",
        severity="warning",
        is_simulated=True,
    )

    # In off mode: both must be hidden
    assert len(hazard_svc.get_active_events()) == 0
    assert len(alert_svc.get_active_alerts()) == 0


def test_real_events_and_alerts_visible_in_all_modes(isolated_services, set_live_mode):
    """Real events (is_simulated=False) remain visible across live, replay, and off modes."""
    hazard_svc: HazardEventService = isolated_services["hazard_svc"]
    alert_svc: AlertService = isolated_services["alert_svc"]
    all_segs = isolated_services["all_segs"]
    target_seg = all_segs[5]

    # Create a real verified report hazard event
    real_event_id = hazard_svc.on_report_status_change(
        report_id="rep_real_001",
        status_value="verified",
        category="landslide",
        segment_id=target_seg,
        actor_id=2,
        is_simulated=False,
    )
    assert real_event_id is not None

    real_alert = alert_svc.create_alert(
        segment_id=target_seg,
        alert_type="closure",
        severity="critical",
        is_simulated=False,
    )
    assert real_alert is not None
    assert real_alert["is_simulated"] is False

    for test_mode in ("live", "replay", "off"):
        set_live_mode(test_mode)
        hazard_svc.invalidate_cache()

        events = hazard_svc.get_active_events()
        assert any(e["id"] == real_event_id and not e["is_simulated"] for e in events)

        alerts = alert_svc.get_active_alerts()
        assert any(a["id"] == real_alert["id"] and not a["is_simulated"] for a in alerts)


def test_journey_planner_isolation_simulated_closure(isolated_services, set_live_mode):
    """Simulated road closures block journey plans in replay mode, but NEVER in live mode."""
    hazard_event_service.init_db()
    live_risk_service.init_db()

    req = JourneyPlanRequest(
        origin="Ramban Gateway",
        destination="Banihal Gateway",
        mode="live",
        date="2026-11-10",
    )
    eval_time = datetime(2026, 11, 10, 12, 0, tzinfo=timezone.utc)

    # 1. Baseline route without hazards: find a segment on the route
    set_live_mode("live")
    hazard_event_service.invalidate_cache()
    baseline_plan = journey_service.plan_journey(req, now=eval_time)
    assert len(baseline_plan.itinerary) > 10
    target_seg = baseline_plan.itinerary[10].segment_id

    # Simulate critical closure on that traversed segment
    hazard_event_service.simulate_event(
        preset="landslide",
        segment_id=target_seg,
        severity="critical",
        duration_hours=24,
        user_id=1,
    )

    # 2. In LIVE mode: simulated closure must NOT block route -> PROCEED
    set_live_mode("live")
    hazard_event_service.invalidate_cache()
    plan_live = journey_service.plan_journey(req, now=eval_time)
    assert plan_live.recommendation != "HOLD"
    assert target_seg not in plan_live.blocking_segments

    # 3. In REPLAY mode: simulated closure DOES block route -> HOLD
    set_live_mode("replay")
    hazard_event_service.invalidate_cache()
    plan_replay = journey_service.plan_journey(req, now=eval_time)
    assert plan_replay.recommendation == "HOLD"
    assert target_seg in plan_replay.blocking_segments
    assert not plan_replay.baseline_route.is_passable


def test_legacy_database_without_is_simulated_column(tmp_path, set_live_mode):
    """Legacy database tables without an is_simulated column load without error, defaulting to False."""
    set_live_mode("live")
    legacy_db = tmp_path / "legacy.db"

    # Create tables omitting is_simulated column
    with sqlite3.connect(str(legacy_db)) as conn:
        conn.execute(
            """
            CREATE TABLE hazard_event (
                id TEXT PRIMARY KEY,
                segment_id TEXT NOT NULL,
                hazard_type TEXT NOT NULL,
                severity TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'active',
                origin TEXT NOT NULL,
                source_report_id TEXT,
                starts_at TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                created_by INTEGER,
                created_at TEXT NOT NULL
            );
            """
        )
        conn.execute(
            """
            INSERT INTO hazard_event VALUES (
                'ev_legacy_1', 'seg_001', 'road_damage', 'medium', 'active',
                'field_report', NULL, '2026-11-10T00:00:00Z', '2099-01-01T00:00:00Z', NULL, '2026-11-10T00:00:00Z'
            );
            """
        )
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
                is_stale_context INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                acknowledged_at TEXT,
                acknowledged_by INTEGER,
                cleared_at TEXT
            );
            """
        )
        conn.execute(
            """
            INSERT INTO alert VALUES (
                'al_legacy_1', 'seg_001', 'hazard_disruption', 'warning',
                'Title EN', 'Title HI', 'Msg EN', 'Msg HI', 'active', 0,
                '2026-11-10T00:00:00Z', NULL, NULL, NULL
            );
            """
        )
        conn.commit()

    storage = WeatherStorage(db_path=str(legacy_db))
    hazard_svc = HazardEventService(storage=storage)
    alert_svc = AlertService(storage=storage)

    # Must not crash, and rows must default to is_simulated=False
    events = hazard_svc.get_active_events()
    assert len(events) == 1
    assert events[0]["id"] == "ev_legacy_1"
    assert events[0]["is_simulated"] is False
    assert events[0]["badge"] == "VERIFIED"

    alerts = alert_svc.get_active_alerts()
    assert len(alerts) == 1
    assert alerts[0]["id"] == "al_legacy_1"
    assert alerts[0]["is_simulated"] is False
