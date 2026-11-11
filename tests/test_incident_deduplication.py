"""Comprehensive verification tests for Task 4:
1. Incident de-duplication rules, identity tracking, raw report retention, severity monotonicity,
   resolve/reject lifecycle consistency, and legacy DB migration.
2. Routing wording accuracy (zero is never mentioned as a cause, distinction between closed,
   stale, unmonitored, high risk, and baseline clear).
3. API clarity: live date substitution response fields and real hazard event journey blocking/clearing.
"""
import os
import sqlite3
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from src.api.config import settings
from src.api.schemas.journey import JourneyPlanRequest
from src.services.hazard_event_service import HazardEventService, VALID_PRESETS
from src.services.report_service import ReportService, ReportStatus
from src.services.weather.storage import WeatherStorage
from src.services.live_risk_service import LiveRiskService
from src.services.journey_service import journey_service


@pytest.fixture
def temp_db(tmp_path):
    """Provides isolated temporary database path."""
    return tmp_path / "test_dedup.db"


@pytest.fixture
def isolated_services(temp_db, monkeypatch):
    """Initializes isolated HazardEventService, ReportService, WeatherStorage, and LiveRiskService."""
    storage = WeatherStorage(db_path=str(temp_db))
    hazard_svc = HazardEventService(storage=storage)
    report_svc = ReportService(db_path=temp_db)
    risk_svc = LiveRiskService(storage=storage)

    # Monkeypatch singletons
    from src.services import hazard_event_service as hes_mod
    from src.services import report_service as rs_mod
    from src.services.weather import storage as ws_mod
    from src.services import live_risk_service as lrs_mod

    monkeypatch.setattr(hes_mod, "hazard_event_service", hazard_svc)
    monkeypatch.setattr(rs_mod, "report_service", report_svc)
    monkeypatch.setattr(ws_mod, "weather_storage", storage)
    monkeypatch.setattr(lrs_mod, "live_risk_service", risk_svc)

    hazard_svc.init_db()
    report_svc._init_db()
    risk_svc.init_db()

    # Seed users table in temp DB for foreign key / reporter checks
    with sqlite3.connect(temp_db) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY,
                username TEXT UNIQUE NOT NULL,
                name TEXT NOT NULL,
                role TEXT NOT NULL
            );
            """
        )
        conn.execute("INSERT OR IGNORE INTO users (id, username, name, role) VALUES (1, 'user1', 'Citizen One', 'user')")
        conn.execute("INSERT OR IGNORE INTO users (id, username, name, role) VALUES (2, 'user2', 'Citizen Two', 'user')")
        conn.execute("INSERT OR IGNORE INTO users (id, username, name, role) VALUES (3, 'patrol1', 'Officer Singh', 'patrol')")
        conn.execute("INSERT OR IGNORE INTO users (id, username, name, role) VALUES (4, 'admin1', 'Super Admin', 'admin')")
        conn.commit()

    all_segs = journey_service._sorted_segment_ids
    return {
        "db_path": temp_db,
        "hazard_svc": hazard_svc,
        "report_svc": report_svc,
        "storage": storage,
        "risk_svc": risk_svc,
        "all_segs": all_segs,
    }


# ==============================================================================
# Part A: Incident De-duplication Tests
# ==============================================================================

def test_deduplication_merges_matching_reports_same_segment_type(isolated_services):
    """Multiple verified reports for same segment and hazard type within 24h link to one primary event."""
    hazard_svc: HazardEventService = isolated_services["hazard_svc"]
    all_segs = isolated_services["all_segs"]
    seg_id = all_segs[10]

    # Report 1 from User 1
    rep1_id = str(uuid.uuid4())
    ev1_id = hazard_svc.on_report_status_change(
        report_id=rep1_id,
        status_value="verified",
        category="landslide",
        segment_id=seg_id,
        actor_id=3,
        is_simulated=False,
    )
    assert ev1_id is not None

    # Report 2 from User 2 (different reporter, same segment, same type)
    rep2_id = str(uuid.uuid4())
    # Mock row in reports for rep2_id
    with sqlite3.connect(isolated_services["db_path"]) as conn:
        conn.execute(
            """
            INSERT INTO reports (id, client_uuid, reporter_id, category, latitude, longitude,
                                nearest_segment_id, status, created_at, updated_at, is_simulated)
            VALUES (?, ?, 2, 'landslide', 33.25, 75.20, ?, 'verified', ?, ?, 0)
            """,
            (rep2_id, str(uuid.uuid4()), seg_id, datetime.now(timezone.utc).isoformat(), datetime.now(timezone.utc).isoformat()),
        )
        conn.commit()

    ev2_id = hazard_svc.on_report_status_change(
        report_id=rep2_id,
        status_value="verified",
        category="landslide",
        segment_id=seg_id,
        actor_id=3,
        is_simulated=False,
    )
    # Both link to the exact same hazard event ID
    assert ev2_id == ev1_id

    # Verify event report_count is 2
    events = hazard_svc.get_active_events()
    assert len(events) == 1
    assert events[0]["id"] == ev1_id
    assert events[0]["report_count"] == 2


def test_deduplication_no_merge_across_different_segments(isolated_services):
    """Reports on different segments never merge, even with identical hazard type and time."""
    hazard_svc: HazardEventService = isolated_services["hazard_svc"]
    all_segs = isolated_services["all_segs"]
    seg_a = all_segs[10]
    seg_b = all_segs[20]

    ev_a = hazard_svc.on_report_status_change(
        report_id=str(uuid.uuid4()),
        status_value="verified",
        category="landslide",
        segment_id=seg_a,
        actor_id=3,
    )
    ev_b = hazard_svc.on_report_status_change(
        report_id=str(uuid.uuid4()),
        status_value="verified",
        category="landslide",
        segment_id=seg_b,
        actor_id=3,
    )
    assert ev_a != ev_b
    events = hazard_svc.get_active_events()
    assert len(events) == 2


def test_deduplication_no_merge_across_different_types(isolated_services):
    """Reports for different hazard types on the same segment do not merge."""
    hazard_svc: HazardEventService = isolated_services["hazard_svc"]
    all_segs = isolated_services["all_segs"]
    seg = all_segs[15]

    ev_landslide = hazard_svc.on_report_status_change(
        report_id=str(uuid.uuid4()),
        status_value="verified",
        category="landslide",
        segment_id=seg,
        actor_id=3,
    )
    ev_damage = hazard_svc.on_report_status_change(
        report_id=str(uuid.uuid4()),
        status_value="verified",
        category="road_damage",
        segment_id=seg,
        actor_id=3,
    )
    assert ev_landslide != ev_damage
    events = hazard_svc.get_active_events()
    assert len(events) == 2


def test_deduplication_no_merge_simulated_vs_real(isolated_services):
    """Real field reports and operator simulations on the same segment never merge."""
    hazard_svc: HazardEventService = isolated_services["hazard_svc"]
    all_segs = isolated_services["all_segs"]
    seg = all_segs[12]

    # Real verified report
    ev_real = hazard_svc.on_report_status_change(
        report_id=str(uuid.uuid4()),
        status_value="verified",
        category="landslide",
        segment_id=seg,
        actor_id=3,
        is_simulated=False,
    )

    # Simulated operator hazard on same segment
    sim_res = hazard_svc.simulate_event(
        preset="landslide",
        segment_id=seg,
        severity="critical",
        user_id=4,
    )

    assert ev_real != sim_res["id"]
    # In live mode (include_simulated=False), only real event is visible
    live_events = hazard_svc.get_active_events(include_simulated=False)
    assert len(live_events) == 1
    assert live_events[0]["id"] == ev_real


def test_same_user_repeat_does_not_inflate_report_count(isolated_services):
    """Repeated submissions by the exact same user link to the primary event but do not inflate report_count."""
    hazard_svc: HazardEventService = isolated_services["hazard_svc"]
    all_segs = isolated_services["all_segs"]
    seg = all_segs[14]

    rep1_id = str(uuid.uuid4())
    rep2_id = str(uuid.uuid4())
    now_iso = datetime.now(timezone.utc).isoformat()

    with sqlite3.connect(isolated_services["db_path"]) as conn:
        # Both reports from reporter_id = 1
        conn.execute(
            """
            INSERT INTO reports (id, client_uuid, reporter_id, category, latitude, longitude,
                                nearest_segment_id, status, created_at, updated_at, is_simulated)
            VALUES (?, ?, 1, 'landslide', 33.25, 75.20, ?, 'verified', ?, ?, 0)
            """,
            (rep1_id, str(uuid.uuid4()), seg, now_iso, now_iso),
        )
        conn.execute(
            """
            INSERT INTO reports (id, client_uuid, reporter_id, category, latitude, longitude,
                                nearest_segment_id, status, created_at, updated_at, is_simulated)
            VALUES (?, ?, 1, 'landslide', 33.25, 75.20, ?, 'verified', ?, ?, 0)
            """,
            (rep2_id, str(uuid.uuid4()), seg, now_iso, now_iso),
        )
        conn.commit()

    ev1 = hazard_svc.on_report_status_change(
        report_id=rep1_id,
        status_value="verified",
        category="landslide",
        segment_id=seg,
        actor_id=3,
    )
    ev2 = hazard_svc.on_report_status_change(
        report_id=rep2_id,
        status_value="verified",
        category="landslide",
        segment_id=seg,
        actor_id=3,
    )
    assert ev1 == ev2
    events = hazard_svc.get_active_events()
    assert len(events) == 1
    # Count remains 1 because reporter_id 1 was already counted
    assert events[0]["report_count"] == 1


def test_raw_reports_kept_and_linked(isolated_services):
    """Every raw report remains in reports table with duplicate_of and hazard_event_id populated."""
    hazard_svc: HazardEventService = isolated_services["hazard_svc"]
    all_segs = isolated_services["all_segs"]
    seg = all_segs[16]

    rep1_id = str(uuid.uuid4())
    rep2_id = str(uuid.uuid4())
    now_iso = datetime.now(timezone.utc).isoformat()

    with sqlite3.connect(isolated_services["db_path"]) as conn:
        conn.execute(
            """
            INSERT INTO reports (id, client_uuid, reporter_id, category, latitude, longitude,
                                nearest_segment_id, status, created_at, updated_at, is_simulated)
            VALUES (?, ?, 1, 'landslide', 33.25, 75.20, ?, 'verified', ?, ?, 0)
            """,
            (rep1_id, str(uuid.uuid4()), seg, now_iso, now_iso),
        )
        conn.execute(
            """
            INSERT INTO reports (id, client_uuid, reporter_id, category, latitude, longitude,
                                nearest_segment_id, status, created_at, updated_at, is_simulated)
            VALUES (?, ?, 2, 'landslide', 33.25, 75.20, ?, 'verified', ?, ?, 0)
            """,
            (rep2_id, str(uuid.uuid4()), seg, now_iso, now_iso),
        )
        conn.commit()

    ev_id = hazard_svc.on_report_status_change(
        report_id=rep1_id,
        status_value="verified",
        category="landslide",
        segment_id=seg,
        actor_id=3,
    )
    hazard_svc.on_report_status_change(
        report_id=rep2_id,
        status_value="verified",
        category="landslide",
        segment_id=seg,
        actor_id=3,
    )

    with sqlite3.connect(isolated_services["db_path"]) as conn:
        conn.row_factory = sqlite3.Row
        r1 = conn.execute("SELECT * FROM reports WHERE id = ?", (rep1_id,)).fetchone()
        r2 = conn.execute("SELECT * FROM reports WHERE id = ?", (rep2_id,)).fetchone()

    assert r1 is not None and r2 is not None
    assert r1["hazard_event_id"] == ev_id
    assert r2["hazard_event_id"] == ev_id
    assert r2["duplicate_of"] == rep1_id


def test_severity_never_lowered_by_duplicate(isolated_services):
    """A duplicate report cannot lower an event's severity; it can only upgrade it."""
    hazard_svc: HazardEventService = isolated_services["hazard_svc"]
    all_segs = isolated_services["all_segs"]
    seg = all_segs[18]

    # Report 1 is critical (landslide)
    rep1_id = str(uuid.uuid4())
    rep2_id = str(uuid.uuid4())
    now_iso = datetime.now(timezone.utc).isoformat()
    with sqlite3.connect(isolated_services["db_path"]) as conn:
        conn.execute(
            """
            INSERT INTO reports (id, client_uuid, reporter_id, category, latitude, longitude,
                                nearest_segment_id, status, created_at, updated_at, is_simulated)
            VALUES (?, ?, 1, 'landslide', 33.25, 75.20, ?, 'verified', ?, ?, 0)
            """,
            (rep1_id, str(uuid.uuid4()), seg, now_iso, now_iso),
        )
        conn.execute(
            """
            INSERT INTO reports (id, client_uuid, reporter_id, category, latitude, longitude,
                                nearest_segment_id, status, created_at, updated_at, is_simulated)
            VALUES (?, ?, 2, 'landslide', 33.25, 75.20, ?, 'verified', ?, ?, 0)
            """,
            (rep2_id, str(uuid.uuid4()), seg, now_iso, now_iso),
        )
        conn.commit()

    ev1 = hazard_svc.on_report_status_change(
        report_id=rep1_id,
        status_value="verified",
        category="landslide",
        segment_id=seg,
        actor_id=3,
    )
    events = hazard_svc.get_active_events()
    assert len(events) == 1
    assert events[0]["severity"] == "critical"

    # Report 2 is also landslide on the same segment (links as duplicate)
    ev2 = hazard_svc.on_report_status_change(
        report_id=rep2_id,
        status_value="verified",
        category="landslide",
        segment_id=seg,
        actor_id=3,
    )
    assert ev2 == ev1
    events = hazard_svc.get_active_events()
    assert len(events) == 1
    # Severity is preserved at critical (never downgraded)
    assert events[0]["severity"] == "critical"
    assert events[0]["report_count"] == 2


def test_resolve_primary_closes_event_and_resolves_linked_reports(isolated_services):
    """Resolving the primary report transitions all linked reports to resolved and closes event."""
    hazard_svc: HazardEventService = isolated_services["hazard_svc"]
    all_segs = isolated_services["all_segs"]
    seg = all_segs[22]

    rep1_id = str(uuid.uuid4())
    rep2_id = str(uuid.uuid4())
    now_iso = datetime.now(timezone.utc).isoformat()

    with sqlite3.connect(isolated_services["db_path"]) as conn:
        conn.execute(
            """
            INSERT INTO reports (id, client_uuid, reporter_id, category, latitude, longitude,
                                nearest_segment_id, status, created_at, updated_at, is_simulated)
            VALUES (?, ?, 1, 'landslide', 33.25, 75.20, ?, 'verified', ?, ?, 0)
            """,
            (rep1_id, str(uuid.uuid4()), seg, now_iso, now_iso),
        )
        conn.execute(
            """
            INSERT INTO reports (id, client_uuid, reporter_id, category, latitude, longitude,
                                nearest_segment_id, status, created_at, updated_at, is_simulated)
            VALUES (?, ?, 2, 'landslide', 33.25, 75.20, ?, 'verified', ?, ?, 0)
            """,
            (rep2_id, str(uuid.uuid4()), seg, now_iso, now_iso),
        )
        conn.commit()

    ev_id = hazard_svc.on_report_status_change(
        report_id=rep1_id,
        status_value="verified",
        category="landslide",
        segment_id=seg,
        actor_id=3,
    )
    hazard_svc.on_report_status_change(
        report_id=rep2_id,
        status_value="verified",
        category="landslide",
        segment_id=seg,
        actor_id=3,
    )

    # Now resolve primary report
    hazard_svc.on_report_status_change(
        report_id=rep1_id,
        status_value="resolved",
        category="landslide",
        segment_id=seg,
        actor_id=3,
    )

    # Active events should now be empty
    active_events = hazard_svc.get_active_events()
    assert len(active_events) == 0

    # Linked reports in reports table should both be resolved
    with sqlite3.connect(isolated_services["db_path"]) as conn:
        conn.row_factory = sqlite3.Row
        r2 = conn.execute("SELECT status FROM reports WHERE id = ?", (rep2_id,)).fetchone()
    assert r2["status"] == "resolved"


def test_reject_duplicate_report_does_not_close_primary_event(isolated_services):
    """Rejecting an individual duplicate report leaves the primary active event intact."""
    hazard_svc: HazardEventService = isolated_services["hazard_svc"]
    all_segs = isolated_services["all_segs"]
    seg = all_segs[24]

    rep1_id = str(uuid.uuid4())
    rep2_id = str(uuid.uuid4())
    now_iso = datetime.now(timezone.utc).isoformat()

    with sqlite3.connect(isolated_services["db_path"]) as conn:
        conn.execute(
            """
            INSERT INTO reports (id, client_uuid, reporter_id, category, latitude, longitude,
                                nearest_segment_id, status, created_at, updated_at, is_simulated)
            VALUES (?, ?, 1, 'landslide', 33.25, 75.20, ?, 'verified', ?, ?, 0)
            """,
            (rep1_id, str(uuid.uuid4()), seg, now_iso, now_iso),
        )
        conn.execute(
            """
            INSERT INTO reports (id, client_uuid, reporter_id, category, latitude, longitude,
                                nearest_segment_id, status, created_at, updated_at, is_simulated)
            VALUES (?, ?, 2, 'landslide', 33.25, 75.20, ?, 'verified', ?, ?, 0)
            """,
            (rep2_id, str(uuid.uuid4()), seg, now_iso, now_iso),
        )
        conn.commit()

    hazard_svc.on_report_status_change(
        report_id=rep1_id,
        status_value="verified",
        category="landslide",
        segment_id=seg,
        actor_id=3,
    )
    hazard_svc.on_report_status_change(
        report_id=rep2_id,
        status_value="verified",
        category="landslide",
        segment_id=seg,
        actor_id=3,
    )

    # Reject rep2
    hazard_svc.on_report_status_change(
        report_id=rep2_id,
        status_value="rejected",
        category="landslide",
        segment_id=seg,
        actor_id=3,
    )

    # Primary event MUST remain active
    events = hazard_svc.get_active_events()
    assert len(events) == 1
    assert events[0]["status"] == "active"


def test_resolved_rejected_expired_events_never_accept_new_linked_reports(isolated_services):
    """Resolved, rejected, and expired events never merge with subsequent reports; a new active event is created."""
    hazard_svc: HazardEventService = isolated_services["hazard_svc"]
    all_segs = isolated_services["all_segs"]
    seg = all_segs[26]

    # 1. Test Resolved Event:
    rep1_id = str(uuid.uuid4())
    now_iso = datetime.now(timezone.utc).isoformat()
    with sqlite3.connect(isolated_services["db_path"]) as conn:
        conn.execute(
            """
            INSERT INTO reports (id, client_uuid, reporter_id, category, latitude, longitude,
                                nearest_segment_id, status, created_at, updated_at, is_simulated)
            VALUES (?, ?, 1, 'landslide', 33.25, 75.20, ?, 'verified', ?, ?, 0)
            """,
            (rep1_id, str(uuid.uuid4()), seg, now_iso, now_iso),
        )
        conn.commit()

    ev1_id = hazard_svc.on_report_status_change(
        report_id=rep1_id,
        status_value="verified",
        category="landslide",
        segment_id=seg,
        actor_id=3,
    )
    # Resolve it -> event becomes closed
    hazard_svc.on_report_status_change(
        report_id=rep1_id,
        status_value="resolved",
        category="landslide",
        segment_id=seg,
        actor_id=3,
    )
    assert len(hazard_svc.get_active_events()) == 0

    # New report on same segment after resolution -> MUST create a brand new event, not link to closed ev1
    rep2_id = str(uuid.uuid4())
    with sqlite3.connect(isolated_services["db_path"]) as conn:
        conn.execute(
            """
            INSERT INTO reports (id, client_uuid, reporter_id, category, latitude, longitude,
                                nearest_segment_id, status, created_at, updated_at, is_simulated)
            VALUES (?, ?, 2, 'landslide', 33.25, 75.20, ?, 'verified', ?, ?, 0)
            """,
            (rep2_id, str(uuid.uuid4()), seg, now_iso, now_iso),
        )
        conn.commit()

    ev2_id = hazard_svc.on_report_status_change(
        report_id=rep2_id,
        status_value="verified",
        category="landslide",
        segment_id=seg,
        actor_id=3,
    )
    assert ev2_id != ev1_id
    active_events = hazard_svc.get_active_events()
    assert len(active_events) == 1
    assert active_events[0]["id"] == ev2_id

    # 2. Test Expired Event:
    # Force event to expire by setting expires_at to past
    past_iso = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
    with sqlite3.connect(isolated_services["db_path"]) as conn:
        conn.execute("UPDATE hazard_event SET status = 'expired', expires_at = ? WHERE id = ?", (past_iso, ev2_id))
        conn.commit()
    hazard_svc.invalidate_cache()
    assert len(hazard_svc.get_active_events()) == 0

    # New report on same segment after expiry -> MUST create a brand new event, not link to expired ev2
    rep3_id = str(uuid.uuid4())
    with sqlite3.connect(isolated_services["db_path"]) as conn:
        conn.execute(
            """
            INSERT INTO reports (id, client_uuid, reporter_id, category, latitude, longitude,
                                nearest_segment_id, status, created_at, updated_at, is_simulated)
            VALUES (?, ?, 1, 'landslide', 33.25, 75.20, ?, 'verified', ?, ?, 0)
            """,
            (rep3_id, str(uuid.uuid4()), seg, now_iso, now_iso),
        )
        conn.commit()

    ev3_id = hazard_svc.on_report_status_change(
        report_id=rep3_id,
        status_value="verified",
        category="landslide",
        segment_id=seg,
        actor_id=3,
    )
    assert ev3_id != ev2_id
    assert ev3_id != ev1_id
    active_events = hazard_svc.get_active_events()
    assert len(active_events) == 1
    assert active_events[0]["id"] == ev3_id


def test_legacy_database_migration_additive_idempotent(tmp_path):
    """Legacy database tables without report_count/duplicate_of columns migrate cleanly."""
    legacy_db = tmp_path / "legacy.db"

    # Create legacy hazard_event and reports schema without Task 4 columns
    with sqlite3.connect(legacy_db) as conn:
        conn.execute(
            """
            CREATE TABLE hazard_event (
                id TEXT PRIMARY KEY,
                segment_id TEXT NOT NULL,
                hazard_type TEXT NOT NULL,
                severity TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'active',
                origin TEXT NOT NULL,
                is_simulated INTEGER NOT NULL DEFAULT 0,
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
                'old-ev-1', 'seg_001', 'landslide', 'critical', 'active', 'field_report',
                0, 'old-rep-1', '2026-11-10T00:00:00Z', '2026-11-11T00:00:00Z', 1, '2026-11-10T00:00:00Z'
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE reports (
                id TEXT PRIMARY KEY,
                client_uuid TEXT UNIQUE NOT NULL,
                reporter_id INTEGER NOT NULL,
                category TEXT NOT NULL,
                description TEXT,
                latitude REAL NOT NULL,
                longitude REAL NOT NULL,
                nearest_segment_id TEXT,
                nearest_segment_distance_m REAL,
                photo_path TEXT,
                status TEXT NOT NULL DEFAULT 'submitted',
                assigned_to INTEGER,
                client_created_at TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                is_simulated INTEGER NOT NULL DEFAULT 0
            );
            """
        )
        conn.commit()

    # Now initialize services against legacy DB
    storage = WeatherStorage(db_path=str(legacy_db))
    hazard_svc = HazardEventService(storage=storage)
    report_svc = ReportService(db_path=legacy_db)
    risk_svc = LiveRiskService(storage=storage)

    hazard_svc.init_db()
    report_svc._init_db()
    risk_svc.init_db()

    # Verify columns were added
    with sqlite3.connect(legacy_db) as conn:
        conn.row_factory = sqlite3.Row
        ev_cols = {c[1] for c in conn.execute("PRAGMA table_info(hazard_event)").fetchall()}
        rep_cols = {c[1] for c in conn.execute("PRAGMA table_info(reports)").fetchall()}
        assert "report_count" in ev_cols
        assert "last_reported_at" in ev_cols
        assert "duplicate_of" in rep_cols
        assert "hazard_event_id" in rep_cols

        row = conn.execute("SELECT * FROM hazard_event WHERE id = 'old-ev-1'").fetchone()
        assert row["report_count"] == 1
        assert row["last_reported_at"] == "2026-11-10T00:00:00Z"

    # Verify get_active_events reads without error
    events = hazard_svc.get_active_events(now=datetime(2026, 11, 10, 12, 0, tzinfo=timezone.utc))
    assert len(events) == 1
    assert events[0]["report_count"] == 1


# ==============================================================================
# Part B: Routing Wording Accuracy Tests
# ==============================================================================

def test_routing_wording_never_mentions_zero_closed_segments():
    """Tradeoff explanation and reasons never print 'blocked by 0 closed segment(s)' when passable."""
    from src.services.journey_service import journey_service
    from src.api.schemas.journey import JourneyPlanRequest

    # Evaluate journey without any closures
    req = JourneyPlanRequest(
        origin="Ramban Gateway",
        destination="Banihal Gateway",
        mode="historical",
        date="2024-03-15",
    )
    res = journey_service.plan_journey(req)
    assert "0 closed" not in res.recommendation_reason
    assert "0 closed" not in (res.baseline_route.trade_off_explanation or "")
    assert "0 closed" not in (res.risk_aware_route.trade_off_explanation or "")


def _seed_live_risk(db_path, all_segs, as_of="2026-11-10", is_stale=0, status="OK", computed_at=None):
    now_iso = computed_at or datetime.now(timezone.utc).isoformat()
    with sqlite3.connect(db_path) as conn:
        for s in all_segs:
            conn.execute(
                """
                INSERT OR REPLACE INTO live_risk (
                    segment_id, as_of, score, tier, status, is_stale,
                    model_version, checkpoint_sha256, weather_window_end, computed_at, source
                ) VALUES (?, ?, 0.05, 'Low', ?, ?, '1.0.0', 'SHA', ?, ?, 'open-meteo')
                """,
                (s, as_of, status, is_stale, as_of, now_iso),
            )
        conn.commit()


def test_routing_wording_distinguishes_stale_telemetry_vs_unmonitored(isolated_services, set_live_mode):
    """When telemetry is stale but missing segments count is 0, reason states 'stale (>24h)', not '0 unmonitored'."""
    set_live_mode("live")
    db_path = isolated_services["db_path"]
    all_segs = isolated_services["all_segs"]
    eval_time = datetime(2026, 11, 10, 12, 0, tzinfo=timezone.utc)
    old_iso = (eval_time - timedelta(hours=30)).isoformat()

    _seed_live_risk(db_path, all_segs, as_of="2026-11-08", is_stale=1, status="STALE_DATA", computed_at=old_iso)
    isolated_services["risk_svc"].invalidate_cache()

    req = JourneyPlanRequest(
        origin="Ramban Gateway",
        destination="Banihal Gateway",
        mode="live",
        date="2026-11-08",
    )
    res = journey_service.plan_journey(req, now=eval_time)
    assert res.recommendation == "NO_DATA"
    assert "Live telemetry for corridor segments is stale (>24h)." in res.recommendation_reason
    assert "0 unmonitored" not in res.recommendation_reason


def test_routing_wording_never_mentions_zero_segments_for_peak_score():
    """Historical and live recommendations never format '0 segment(s)' when evaluated."""
    req = JourneyPlanRequest(
        origin="Ramban Gateway",
        destination="Banihal Gateway",
        mode="historical",
        date="2023-07-09",
    )
    res = journey_service.plan_journey(req)
    # Check all fields for 0 segment mentions
    assert "0 segment" not in res.recommendation_reason
    assert "0 closed" not in res.recommendation_reason


# ==============================================================================
# Part C: API Clarity Tests
# ==============================================================================

def test_live_mode_date_substitution_fields(isolated_services, set_live_mode):
    """In live mode, substituting an unavailable requested date returns date_substituted=True and actual_date."""
    set_live_mode("live")
    db_path = isolated_services["db_path"]
    all_segs = isolated_services["all_segs"]
    eval_time = datetime(2026, 11, 10, 12, 0, tzinfo=timezone.utc)
    now_iso = eval_time.isoformat()

    _seed_live_risk(db_path, all_segs, as_of="2026-11-10", is_stale=0, status="OK", computed_at=now_iso)
    isolated_services["risk_svc"].invalidate_cache()

    # Request journey with old/unsupported date '2023-07-09' in live mode
    req = JourneyPlanRequest(
        origin="Ramban Gateway",
        destination="Banihal Gateway",
        mode="live",
        date="2023-07-09",
    )
    res = journey_service.plan_journey(req, now=eval_time)

    # Verify additive fields
    assert res.date_substituted is True
    assert res.requested_date == "2023-07-09"
    assert res.actual_date == "2026-11-10"


def test_live_mode_journey_reflects_real_hazard_and_clears_on_resolve(isolated_services, set_live_mode):
    """Live journey planner reflects a REAL (non-simulated) hazard report/verify path and clears on resolve."""
    set_live_mode("live")
    db_path = isolated_services["db_path"]
    hazard_svc: HazardEventService = isolated_services["hazard_svc"]
    all_segs = isolated_services["all_segs"]
    target_seg = all_segs[60]
    eval_time = datetime(2026, 11, 10, 12, 0, tzinfo=timezone.utc)
    now_iso = eval_time.isoformat()

    # 1. Seed fresh live risk
    _seed_live_risk(db_path, all_segs, as_of="2026-11-10", is_stale=0, status="OK", computed_at=now_iso)
    isolated_services["risk_svc"].invalidate_cache()

    req = JourneyPlanRequest(
        origin="Ramban Gateway",
        destination="Banihal Gateway",
        mode="live",
        date="2026-11-10",
    )

    # Initial plan is PASSABLE
    initial_res = journey_service.plan_journey(req, now=eval_time)
    assert initial_res.baseline_route.is_passable is True
    assert initial_res.recommendation == "PROCEED"

    # 2. Citizen submits real field report (is_simulated = False) on target_seg
    rep_id = str(uuid.uuid4())
    now_iso = eval_time.isoformat()
    with sqlite3.connect(isolated_services["db_path"]) as conn:
        conn.execute(
            """
            INSERT INTO reports (id, client_uuid, reporter_id, category, latitude, longitude,
                                nearest_segment_id, status, created_at, updated_at, is_simulated)
            VALUES (?, ?, 1, 'landslide', 33.25, 75.20, ?, 'submitted', ?, ?, 0)
            """,
            (rep_id, str(uuid.uuid4()), target_seg, now_iso, now_iso),
        )
        conn.commit()

    # While submitted (unverified), live journey plan is NOT blocked
    unverified_res = journey_service.plan_journey(req, now=eval_time)
    assert unverified_res.baseline_route.is_passable is True

    # 3. Patrol verifies report -> creates real hazard event
    hazard_svc.on_report_status_change(
        report_id=rep_id,
        status_value="verified",
        category="landslide",
        segment_id=target_seg,
        actor_id=3,
        is_simulated=False,
    )

    # Very next live journey plan MUST reflect the real hazard closure
    blocked_res = journey_service.plan_journey(req, now=eval_time)
    assert blocked_res.baseline_route.is_passable is False
    assert target_seg in blocked_res.blocking_segments
    assert blocked_res.recommendation == "HOLD"
    assert "is CLOSED" in blocked_res.recommendation_reason

    # 4. Resolve the report
    hazard_svc.on_report_status_change(
        report_id=rep_id,
        status_value="resolved",
        category="landslide",
        segment_id=target_seg,
        actor_id=3,
        is_simulated=False,
    )

    # Very next live journey plan MUST be clear again
    cleared_res = journey_service.plan_journey(req, now=eval_time)
    assert cleared_res.baseline_route.is_passable is True
    assert len(cleared_res.blocking_segments) == 0
    assert cleared_res.recommendation == "PROCEED"


def test_guest_report_stored_and_linked_without_raising_report_count(isolated_services):
    """Guest reports (reporter_id=0) are preserved and linked but do not increment report_count."""
    hazard_svc: HazardEventService = isolated_services["hazard_svc"]
    all_segs = isolated_services["all_segs"]
    seg = all_segs[18]
    now_iso = datetime.now(timezone.utc).isoformat()

    primary_id = str(uuid.uuid4())
    guest_id = str(uuid.uuid4())

    with sqlite3.connect(isolated_services["db_path"]) as conn:
        conn.execute(
            """
            INSERT INTO reports (id, client_uuid, reporter_id, category, latitude, longitude,
                                nearest_segment_id, status, created_at, updated_at, is_simulated)
            VALUES (?, ?, 1, 'landslide', 33.25, 75.20, ?, 'verified', ?, ?, 0)
            """,
            (primary_id, str(uuid.uuid4()), seg, now_iso, now_iso),
        )
        # Guest report (reporter_id = 0)
        conn.execute(
            """
            INSERT INTO reports (id, client_uuid, reporter_id, category, latitude, longitude,
                                nearest_segment_id, status, created_at, updated_at, is_simulated)
            VALUES (?, ?, 0, 'landslide', 33.25, 75.20, ?, 'verified', ?, ?, 0)
            """,
            (guest_id, str(uuid.uuid4()), seg, now_iso, now_iso),
        )
        conn.commit()

    ev1 = hazard_svc.on_report_status_change(
        report_id=primary_id,
        status_value="verified",
        category="landslide",
        segment_id=seg,
        actor_id=3,
    )
    assert ev1 is not None

    ev2 = hazard_svc.on_report_status_change(
        report_id=guest_id,
        status_value="verified",
        category="landslide",
        segment_id=seg,
        actor_id=3,
    )
    assert ev2 == ev1

    events = hazard_svc.get_active_events()
    assert len(events) == 1
    # report_count must not be inflated by guest report
    assert events[0]["report_count"] == 1

    # Raw guest report is preserved and linked
    with sqlite3.connect(isolated_services["db_path"]) as conn:
        conn.row_factory = sqlite3.Row
        guest_row = conn.execute("SELECT * FROM reports WHERE id = ?", (guest_id,)).fetchone()
        assert guest_row["hazard_event_id"] == ev1
        assert guest_row["duplicate_of"] == primary_id


def test_new_report_after_primary_rejected_creates_new_event(isolated_services):
    """When a primary report is rejected, subsequent report on the same segment creates a brand new event."""
    hazard_svc: HazardEventService = isolated_services["hazard_svc"]
    all_segs = isolated_services["all_segs"]
    seg = all_segs[20]
    now_iso = datetime.now(timezone.utc).isoformat()

    rep1_id = str(uuid.uuid4())
    rep2_id = str(uuid.uuid4())

    with sqlite3.connect(isolated_services["db_path"]) as conn:
        conn.execute(
            """
            INSERT INTO reports (id, client_uuid, reporter_id, category, latitude, longitude,
                                nearest_segment_id, status, created_at, updated_at, is_simulated)
            VALUES (?, ?, 1, 'landslide', 33.25, 75.20, ?, 'verified', ?, ?, 0)
            """,
            (rep1_id, str(uuid.uuid4()), seg, now_iso, now_iso),
        )
        conn.commit()

    ev1_id = hazard_svc.on_report_status_change(
        report_id=rep1_id,
        status_value="verified",
        category="landslide",
        segment_id=seg,
        actor_id=3,
    )
    assert len(hazard_svc.get_active_events()) == 1

    # Reject primary report -> closes ev1
    hazard_svc.on_report_status_change(
        report_id=rep1_id,
        status_value="rejected",
        category="landslide",
        segment_id=seg,
        actor_id=3,
    )
    assert len(hazard_svc.get_active_events()) == 0

    # New report submitted on same segment
    with sqlite3.connect(isolated_services["db_path"]) as conn:
        conn.execute(
            """
            INSERT INTO reports (id, client_uuid, reporter_id, category, latitude, longitude,
                                nearest_segment_id, status, created_at, updated_at, is_simulated)
            VALUES (?, ?, 2, 'landslide', 33.25, 75.20, ?, 'verified', ?, ?, 0)
            """,
            (rep2_id, str(uuid.uuid4()), seg, now_iso, now_iso),
        )
        conn.commit()

    ev2_id = hazard_svc.on_report_status_change(
        report_id=rep2_id,
        status_value="verified",
        category="landslide",
        segment_id=seg,
        actor_id=3,
    )
    assert ev2_id is not None
    assert ev2_id != ev1_id
    active_events = hazard_svc.get_active_events()
    assert len(active_events) == 1
    assert active_events[0]["id"] == ev2_id


def test_primary_report_rejection_consequences_and_duplicate_retention(isolated_services):
    """When a primary report is rejected:
    1. Hazard event status becomes 'closed'.
    2. Primary report status becomes 'rejected'.
    3. Duplicate promotion is absent: event source_report_id remains rep1.id.
    4. Linked duplicate reports retain their statuses ('verified' or 'submitted') and links.
    5. Event report_count and last_reported_at remain unchanged.
    6. Subsequent report on that segment creates a fresh event (excluded from dedup).
    """
    report_svc = isolated_services["report_svc"]
    hazard_svc = isolated_services["hazard_svc"]
    all_segs = isolated_services["all_segs"]
    seg = all_segs[10]

    from src.api.schemas.auth import UserProfile, UserRole
    user1 = UserProfile(id=1, email="u1@test.com", name="User 1", role=UserRole.USER.value, preferred_vehicle="Car", created_at="2026-11-10T00:00:00Z")
    user2 = UserProfile(id=2, email="u2@test.com", name="User 2", role=UserRole.USER.value, preferred_vehicle="Car", created_at="2026-11-10T00:00:00Z")
    user3 = UserProfile(id=3, email="u3@test.com", name="User 3", role=UserRole.USER.value, preferred_vehicle="Car", created_at="2026-11-10T00:00:00Z")
    user4 = UserProfile(id=4, email="u4@test.com", name="User 4", role=UserRole.USER.value, preferred_vehicle="Car", created_at="2026-11-10T00:00:00Z")
    patrol = UserProfile(id=5, email="p@test.com", name="Patrol Officer", role=UserRole.PATROL.value, preferred_vehicle="Car", created_at="2026-11-10T00:00:00Z")

    with sqlite3.connect(isolated_services["db_path"]) as conn:
        coords = conn.execute("SELECT latitude, longitude FROM reports WHERE nearest_segment_id = ? LIMIT 1", (seg,)).fetchone()
    lat = coords[0] if coords else 33.24
    lon = coords[1] if coords else 75.24

    # 1. Primary report submitted & verified
    rep1 = report_svc.create_report(
        client_uuid=str(uuid.uuid4()),
        category="landslide",
        description="Rockfall blocking corridor",
        latitude=lat,
        longitude=lon,
        client_created_at=None,
        photo=None,
        reporter=user1,
    )
    report_svc.update_report_status(
        report_id=rep1.id,
        new_status="verified",
        note=None,
        actor=patrol,
    )
    r1 = report_svc.get_report_by_id(rep1.id, patrol)
    ev_id = r1.hazard_event_id
    assert ev_id is not None

    # 2. Duplicate 1 submitted & verified
    rep2 = report_svc.create_report(
        client_uuid=str(uuid.uuid4()),
        category="landslide",
        description="Same rockfall observed",
        latitude=lat,
        longitude=lon,
        client_created_at=None,
        photo=None,
        reporter=user2,
    )
    assert rep2.duplicate_of == rep1.id
    assert rep2.hazard_event_id == ev_id
    report_svc.update_report_status(
        report_id=rep2.id,
        new_status="verified",
        note=None,
        actor=patrol,
    )

    # 3. Duplicate 2 submitted (remains unverified / submitted)
    rep3 = report_svc.create_report(
        client_uuid=str(uuid.uuid4()),
        category="landslide",
        description="Rockfall still there",
        latitude=lat,
        longitude=lon,
        client_created_at=None,
        photo=None,
        reporter=user3,
    )
    assert rep3.duplicate_of == rep1.id
    assert rep3.hazard_event_id == ev_id
    assert rep3.status == "submitted"

    # Capture event state before rejection
    with sqlite3.connect(isolated_services["db_path"]) as conn:
        conn.row_factory = sqlite3.Row
        ev_before = conn.execute(
            "SELECT status, source_report_id, report_count, last_reported_at FROM hazard_event WHERE id = ?",
            (ev_id,),
        ).fetchone()
    assert ev_before["status"] == "active"
    assert ev_before["report_count"] == 2
    count_before = ev_before["report_count"]
    last_rep_before = ev_before["last_reported_at"]

    # 4. Reject the primary report (with required note)
    report_svc.update_report_status(
        report_id=rep1.id,
        new_status="rejected",
        note="Field inspection: false alarm / clear road",
        actor=patrol,
    )

    # Assert consequence 1: Primary report status == 'rejected'
    r1_after = report_svc.get_report_by_id(rep1.id, patrol)
    assert r1_after.status == "rejected"

    # Assert consequence 2 & 3: Hazard event status == 'closed' and no duplicate promotion
    with sqlite3.connect(isolated_services["db_path"]) as conn:
        conn.row_factory = sqlite3.Row
        ev_after = conn.execute(
            "SELECT status, source_report_id, report_count, last_reported_at FROM hazard_event WHERE id = ?",
            (ev_id,),
        ).fetchone()
    assert ev_after["status"] == "closed"
    assert ev_after["source_report_id"] == rep1.id

    # Assert consequence 4: Linked duplicates retain statuses and links
    r2_after = report_svc.get_report_by_id(rep2.id, patrol)
    r3_after = report_svc.get_report_by_id(rep3.id, patrol)
    assert r2_after.status == "verified"
    assert r2_after.duplicate_of == rep1.id
    assert r2_after.hazard_event_id == ev_id
    assert r3_after.status == "submitted"
    assert r3_after.duplicate_of == rep1.id
    assert r3_after.hazard_event_id == ev_id

    # Assert consequence 5: Event report_count and last_reported_at remain unchanged
    assert ev_after["report_count"] == count_before
    assert ev_after["last_reported_at"] == last_rep_before

    # Assert consequence 6: Subsequent report on that segment creates a fresh event (excluded from dedup)
    rep4 = report_svc.create_report(
        client_uuid=str(uuid.uuid4()),
        category="landslide",
        description="Fresh new rockfall on same segment",
        latitude=lat,
        longitude=lon,
        client_created_at=None,
        photo=None,
        reporter=user4,
    )
    assert rep4.duplicate_of is None
    assert rep4.hazard_event_id is None

    report_svc.update_report_status(
        report_id=rep4.id,
        new_status="verified",
        note=None,
        actor=patrol,
    )
    r4_after = report_svc.get_report_by_id(rep4.id, patrol)
    assert r4_after.hazard_event_id is not None
    assert r4_after.hazard_event_id != ev_id
    active_events = hazard_svc.get_active_events()
    assert len(active_events) == 1
    assert active_events[0]["id"] == r4_after.hazard_event_id


def test_duplicate_report_creates_no_second_alert_and_no_second_broadcast(isolated_services):
    """Deduplicated reports emit 'update' broadcast (never duplicate 'create') and generate no duplicate alerts."""
    from src.services.alert_service import AlertService
    hazard_svc: HazardEventService = isolated_services["hazard_svc"]
    alert_svc = AlertService(storage=hazard_svc.storage)
    all_segs = isolated_services["all_segs"]
    seg = all_segs[22]
    now_iso = datetime.now(timezone.utc).isoformat()

    broadcasts = []
    hazard_svc._broadcast_event_change = lambda action, event_id: broadcasts.append((action, event_id))

    rep1_id = str(uuid.uuid4())
    rep2_id = str(uuid.uuid4())

    with sqlite3.connect(isolated_services["db_path"]) as conn:
        conn.execute(
            """
            INSERT INTO reports (id, client_uuid, reporter_id, category, latitude, longitude,
                                nearest_segment_id, status, created_at, updated_at, is_simulated)
            VALUES (?, ?, 1, 'landslide', 33.25, 75.20, ?, 'verified', ?, ?, 0)
            """,
            (rep1_id, str(uuid.uuid4()), seg, now_iso, now_iso),
        )
        conn.commit()

    ev1_id = hazard_svc.on_report_status_change(
        report_id=rep1_id,
        status_value="verified",
        category="landslide",
        segment_id=seg,
        actor_id=3,
    )
    # Generates initial closure alert
    alert1 = alert_svc.create_alert(segment_id=seg, alert_type="closure", severity="critical")
    assert alert1 is not None

    assert ("create", ev1_id) in broadcasts
    broadcasts.clear()

    # Verify duplicate report from another user on same segment
    with sqlite3.connect(isolated_services["db_path"]) as conn:
        conn.execute(
            """
            INSERT INTO reports (id, client_uuid, reporter_id, category, latitude, longitude,
                                nearest_segment_id, status, created_at, updated_at, is_simulated)
            VALUES (?, ?, 2, 'landslide', 33.25, 75.20, ?, 'verified', ?, ?, 0)
            """,
            (rep2_id, str(uuid.uuid4()), seg, now_iso, now_iso),
        )
        conn.commit()

    ev2_id = hazard_svc.on_report_status_change(
        report_id=rep2_id,
        status_value="verified",
        category="landslide",
        segment_id=seg,
        actor_id=3,
    )
    assert ev2_id == ev1_id
    # Broadcast must be "refresh" (updating existing event), NOT "create"
    assert ("create", ev1_id) not in broadcasts
    assert ("refresh", ev1_id) in broadcasts

    # Attempting to generate closure alert again is deduplicated
    alert2 = alert_svc.create_alert(segment_id=seg, alert_type="closure", severity="critical")
    assert alert2 is None  # Blocked by alert deduplication


def test_route_reason_never_cites_zero_for_closed_segments():
    """Route reason never prints '0 closed segment(s)' or 'blocked by 0 closed segments'."""
    req = JourneyPlanRequest(
        origin="Ramban Gateway",
        destination="Banihal Gateway",
        mode="historical",
        date="2024-03-15",
    )
    res = journey_service.plan_journey(req)
    assert "0 closed" not in res.recommendation_reason
    assert "blocked by 0" not in res.recommendation_reason


def test_route_reason_never_cites_zero_for_unknown_or_stale_segments(isolated_services, set_live_mode):
    """When telemetry is stale, reason states stale status and never prints '0 unmonitored'."""
    set_live_mode("live")
    db_path = isolated_services["db_path"]
    all_segs = isolated_services["all_segs"]
    eval_time = datetime(2026, 11, 10, 12, 0, tzinfo=timezone.utc)
    old_iso = (eval_time - timedelta(hours=30)).isoformat()

    _seed_live_risk(db_path, all_segs, as_of="2026-11-08", is_stale=1, status="STALE_DATA", computed_at=old_iso)
    isolated_services["risk_svc"].invalidate_cache()

    req = JourneyPlanRequest(
        origin="Ramban Gateway",
        destination="Banihal Gateway",
        mode="live",
        date="2026-11-08",
    )
    res = journey_service.plan_journey(req, now=eval_time)
    assert "0 unmonitored" not in res.recommendation_reason
    assert "0 stale" not in res.recommendation_reason


def test_route_reason_never_cites_zero_for_high_risk_segments():
    """Historical and live plans never format 'High risk detected on 0 segment(s)'."""
    for test_date in ("2023-07-09", "2024-03-15"):
        req = JourneyPlanRequest(
            origin="Ramban Gateway",
            destination="Banihal Gateway",
            mode="historical",
            date=test_date,
        )
        res = journey_service.plan_journey(req)
        assert "detected on 0 segment" not in res.recommendation_reason
        assert "0 high risk" not in res.recommendation_reason


def test_route_reason_never_cites_zero_for_hazard_on_route(isolated_services, set_live_mode):
    """Elevated/hazard recommendations never cite '0 hazard' or '0 segment(s)'."""
    set_live_mode("live")
    req = JourneyPlanRequest(
        origin="Ramban Gateway",
        destination="Banihal Gateway",
        mode="historical",
        date="2024-03-15",
    )
    res = journey_service.plan_journey(req)
    assert "0 hazard" not in res.recommendation_reason
    assert "0 segment" not in res.recommendation_reason


def test_route_reason_never_cites_zero_for_no_data(isolated_services, set_live_mode):
    """When no telemetry is available, route reason never cites 0 segments."""
    set_live_mode("live")
    eval_time = datetime(2026, 11, 10, 12, 0, tzinfo=timezone.utc)
    req = JourneyPlanRequest(
        origin="Ramban Gateway",
        destination="Banihal Gateway",
        mode="live",
        date="2026-11-10",
    )
    res = journey_service.plan_journey(req, now=eval_time)
    assert "0 segment" not in res.recommendation_reason


def test_unmapped_categories_never_merge_with_each_other_or_road_damage(isolated_services):
    """Two different unmapped categories on the same segment create separate events and never merge into road_damage."""
    hazard_svc: HazardEventService = isolated_services["hazard_svc"]
    all_segs = isolated_services["all_segs"]
    seg = all_segs[24]
    now_iso = datetime.now(timezone.utc).isoformat()

    rep1_id = str(uuid.uuid4())
    rep2_id = str(uuid.uuid4())
    rep3_id = str(uuid.uuid4())

    with sqlite3.connect(isolated_services["db_path"]) as conn:
        conn.execute(
            """
            INSERT INTO reports (id, client_uuid, reporter_id, category, latitude, longitude,
                                nearest_segment_id, status, created_at, updated_at, is_simulated)
            VALUES (?, ?, 1, 'landslide', 33.25, 75.20, ?, 'verified', ?, ?, 0)
            """,
            (rep1_id, str(uuid.uuid4()), seg, now_iso, now_iso),
        )
        conn.execute(
            """
            INSERT INTO reports (id, client_uuid, reporter_id, category, latitude, longitude,
                                nearest_segment_id, status, created_at, updated_at, is_simulated)
            VALUES (?, ?, 2, 'flooding', 33.25, 75.20, ?, 'verified', ?, ?, 0)
            """,
            (rep2_id, str(uuid.uuid4()), seg, now_iso, now_iso),
        )
        conn.execute(
            """
            INSERT INTO reports (id, client_uuid, reporter_id, category, latitude, longitude,
                                nearest_segment_id, status, created_at, updated_at, is_simulated)
            VALUES (?, ?, 3, 'road_damage', 33.25, 75.20, ?, 'verified', ?, ?, 0)
            """,
            (rep3_id, str(uuid.uuid4()), seg, now_iso, now_iso),
        )
        conn.commit()

    ev1 = hazard_svc.on_report_status_change(
        report_id=rep1_id,
        status_value="verified",
        category="landslide",
        segment_id=seg,
        actor_id=3,
    )
    ev2 = hazard_svc.on_report_status_change(
        report_id=rep2_id,
        status_value="verified",
        category="flooding",
        segment_id=seg,
        actor_id=3,
    )
    ev3 = hazard_svc.on_report_status_change(
        report_id=rep3_id,
        status_value="verified",
        category="road_damage",
        segment_id=seg,
        actor_id=3,
    )

    # All three events on the same segment must remain distinct
    assert ev1 != ev2
    assert ev1 != ev3
    assert ev2 != ev3

    active_events = {e["id"]: e for e in hazard_svc.get_active_events()}
    assert active_events[ev1]["hazard_type"] == "landslide"
    assert active_events[ev2]["hazard_type"] == "flooding"
    assert active_events[ev3]["hazard_type"] == "road_damage"


# ==============================================================================
# Part D: Section 1 Database Safety & Legacy Migration Tests
# ==============================================================================

def test_legacy_schema_without_additive_columns_remains_readable(tmp_path):
    """Legacy databases without duplicate_of and hazard_event_id remain readable by ReportService queries."""
    import pyproj
    legacy_db = tmp_path / "legacy_readonly.db"
    with sqlite3.connect(legacy_db) as conn:
        conn.execute(
            """
            CREATE TABLE users (id INTEGER PRIMARY KEY, email TEXT, name TEXT, role TEXT);
            """
        )
        conn.execute("INSERT INTO users VALUES (1, 'u@test.com', 'User One', 'user')")
        conn.execute(
            """
            CREATE TABLE reports (
                id TEXT PRIMARY KEY,
                client_uuid TEXT UNIQUE NOT NULL,
                reporter_id INTEGER NOT NULL,
                category TEXT NOT NULL,
                description TEXT,
                latitude REAL NOT NULL,
                longitude REAL NOT NULL,
                nearest_segment_id TEXT,
                nearest_segment_distance_m REAL,
                photo_path TEXT,
                status TEXT NOT NULL DEFAULT 'submitted',
                assigned_to INTEGER,
                client_created_at TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                is_simulated INTEGER NOT NULL DEFAULT 0
            );
            """
        )
        conn.execute(
            """
            CREATE TABLE report_status_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                report_id TEXT NOT NULL,
                from_status TEXT,
                to_status TEXT NOT NULL,
                actor_id INTEGER NOT NULL,
                actor_role TEXT NOT NULL,
                note TEXT,
                timestamp TEXT NOT NULL
            );
            """
        )
        now_iso = datetime.now(timezone.utc).isoformat()
        conn.execute(
            """
            INSERT INTO reports (id, client_uuid, reporter_id, category, latitude, longitude,
                                 nearest_segment_id, status, created_at, updated_at)
            VALUES ('rep_leg_1', 'uuid_leg_1', 1, 'landslide', 33.25, 75.20, 'seg_0', 'verified', ?, ?)
            """,
            (now_iso, now_iso),
        )
        conn.commit()

    # Bypassing _init_db DDL migration by instantiating directly
    svc = ReportService.__new__(ReportService)
    svc.db_path = legacy_db
    svc.graph_path = Path("nh44_corridor_graph.graphml")
    svc.uploads_dir = tmp_path / "uploads"
    svc._transformer = pyproj.Transformer.from_crs("EPSG:4326", "EPSG:32643", always_xy=True)
    svc._segment_geometries = []

    # Read operations must succeed and return valid objects with None for additive columns
    user_reps = svc.get_user_reports(1)
    assert len(user_reps) == 1
    assert user_reps[0].id == "rep_leg_1"
    assert user_reps[0].duplicate_of is None
    assert user_reps[0].hazard_event_id is None

    patrol_reps = svc.get_patrol_reports()
    assert patrol_reps.total == 1
    assert patrol_reps.items[0].duplicate_of is None

    public_reps = svc.get_public_reports()
    assert len(public_reps) == 1
    assert public_reps[0].id == "rep_leg_1"

    stats = svc.get_summary_stats()
    assert stats.verified == 1


def test_additive_migration_and_idempotency_on_temporary_db(tmp_path):
    """Additive migration applies cleanly and idempotently to a legacy database."""
    import pyproj
    legacy_db = tmp_path / "legacy_migrate.db"
    with sqlite3.connect(legacy_db) as conn:
        conn.execute(
            """
            CREATE TABLE reports (
                id TEXT PRIMARY KEY,
                client_uuid TEXT UNIQUE NOT NULL,
                reporter_id INTEGER NOT NULL,
                category TEXT NOT NULL,
                description TEXT,
                latitude REAL NOT NULL,
                longitude REAL NOT NULL,
                nearest_segment_id TEXT,
                nearest_segment_distance_m REAL,
                photo_path TEXT,
                status TEXT NOT NULL DEFAULT 'submitted',
                assigned_to INTEGER,
                client_created_at TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                is_simulated INTEGER NOT NULL DEFAULT 0
            );
            """
        )
        conn.commit()

    svc = ReportService.__new__(ReportService)
    svc.db_path = legacy_db
    svc.graph_path = Path("nh44_corridor_graph.graphml")
    svc.uploads_dir = tmp_path / "uploads"
    svc._transformer = pyproj.Transformer.from_crs("EPSG:4326", "EPSG:32643", always_xy=True)
    svc._segment_geometries = []

    # Apply migration first time
    svc.apply_additive_migration()

    with sqlite3.connect(legacy_db) as conn:
        cols = {c[1] for c in conn.execute("PRAGMA table_info(reports)").fetchall()}
        assert "duplicate_of" in cols
        assert "hazard_event_id" in cols
        indexes = {r[1] for r in conn.execute("PRAGMA index_list(reports)").fetchall()}
        assert "idx_reports_duplicate_of" in indexes
        assert "idx_reports_hazard_event" in indexes

    # Idempotency: run second time without error
    svc.apply_additive_migration()


def test_successful_report_submission_after_migration(tmp_path):
    """After additive migration, report creation succeeds and populates additive columns."""
    from src.api.schemas.auth import UserProfile
    legacy_db = tmp_path / "legacy_submit.db"
    with sqlite3.connect(legacy_db) as conn:
        conn.execute(
            """
            CREATE TABLE users (id INTEGER PRIMARY KEY, email TEXT, name TEXT, role TEXT);
            """
        )
        conn.execute("INSERT INTO users VALUES (1, 'u@test.com', 'User One', 'user')")
        conn.execute(
            """
            CREATE TABLE reports (
                id TEXT PRIMARY KEY,
                client_uuid TEXT UNIQUE NOT NULL,
                reporter_id INTEGER NOT NULL,
                category TEXT NOT NULL,
                description TEXT,
                latitude REAL NOT NULL,
                longitude REAL NOT NULL,
                nearest_segment_id TEXT,
                nearest_segment_distance_m REAL,
                photo_path TEXT,
                status TEXT NOT NULL DEFAULT 'submitted',
                assigned_to INTEGER,
                client_created_at TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                is_simulated INTEGER NOT NULL DEFAULT 0
            );
            """
        )
        conn.execute(
            """
            CREATE TABLE report_status_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                report_id TEXT NOT NULL,
                from_status TEXT,
                to_status TEXT NOT NULL,
                actor_id INTEGER NOT NULL,
                actor_role TEXT NOT NULL,
                note TEXT,
                timestamp TEXT NOT NULL
            );
            """
        )
        conn.commit()

    svc = ReportService(db_path=legacy_db, uploads_dir=tmp_path / "uploads")
    user = UserProfile(id=1, email="u@test.com", name="User One", role="user", preferred_vehicle="Car", created_at="2026-11-10T00:00:00Z")

    res = svc.create_report(
        client_uuid=str(uuid.uuid4()),
        category="landslide",
        description="Active rockfall after rain",
        latitude=33.25,
        longitude=75.20,
        client_created_at=None,
        photo=None,
        reporter=user,
    )
    assert res.id is not None
    assert res.category == "landslide"
    assert res.status == "submitted"


def test_clear_failure_before_incompatible_insert_when_migration_unavailable(tmp_path):
    """ReportService.create_report raises RuntimeError clearly before attempting incompatible insert on unmigrated schema."""
    import pyproj
    from src.api.schemas.auth import UserProfile
    legacy_db = tmp_path / "legacy_unmigrated.db"
    with sqlite3.connect(legacy_db) as conn:
        conn.execute(
            """
            CREATE TABLE users (id INTEGER PRIMARY KEY, email TEXT, name TEXT, role TEXT);
            """
        )
        conn.execute("INSERT INTO users VALUES (1, 'u@test.com', 'User One', 'user')")
        conn.execute(
            """
            CREATE TABLE reports (
                id TEXT PRIMARY KEY,
                client_uuid TEXT UNIQUE NOT NULL,
                reporter_id INTEGER NOT NULL,
                category TEXT NOT NULL,
                description TEXT,
                latitude REAL NOT NULL,
                longitude REAL NOT NULL,
                nearest_segment_id TEXT,
                nearest_segment_distance_m REAL,
                photo_path TEXT,
                status TEXT NOT NULL DEFAULT 'submitted',
                assigned_to INTEGER,
                client_created_at TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                is_simulated INTEGER NOT NULL DEFAULT 0
            );
            """
        )
        conn.commit()

    # Instantiate without calling _init_db
    svc = ReportService.__new__(ReportService)
    svc.db_path = legacy_db
    svc.graph_path = Path("nh44_corridor_graph.graphml")
    svc.uploads_dir = tmp_path / "uploads"
    svc._transformer = pyproj.Transformer.from_crs("EPSG:4326", "EPSG:32643", always_xy=True)
    svc._segment_geometries = []

    user = UserProfile(id=1, email="u@test.com", name="User One", role="user", preferred_vehicle="Car", created_at="2026-11-10T00:00:00Z")

    with pytest.raises(RuntimeError) as exc_info:
        svc.create_report(
            client_uuid=str(uuid.uuid4()),
            category="landslide",
            description="Test failure",
            latitude=33.25,
            longitude=75.20,
            client_created_at=None,
            photo=None,
            reporter=user,
        )
    assert "Schema incompatible" in str(exc_info.value)
    assert "missing required additive columns" in str(exc_info.value)


def test_default_database_resolution_blocks_writes_to_protected_database():
    """ReportService blocks report writes and migrations against the protected historical database."""
    import hashlib
    from src.api.schemas.auth import UserProfile
    protected_db = Path("data/routewise_local.db")
    assert protected_db.exists(), "Protected DB must exist"

    def compute_hash():
        h = hashlib.sha256()
        with open(protected_db, "rb") as f:
            while chunk := f.read(65536):
                h.update(chunk)
        return h.hexdigest()

    sha_before = compute_hash()

    svc = ReportService(db_path=protected_db)
    user = UserProfile(id=1, email="admin@test.com", name="Admin", role="admin", preferred_vehicle="Car", created_at="2026-11-10T00:00:00Z")

    # Attempting to write reports to protected DB must raise PermissionError
    with pytest.raises(PermissionError) as exc_rep:
        svc.create_report(
            client_uuid=str(uuid.uuid4()),
            category="landslide",
            description="Blocked attempt",
            latitude=33.25,
            longitude=75.20,
            client_created_at=None,
            photo=None,
            reporter=user,
        )
    assert "Cannot write reports to protected historical database" in str(exc_rep.value)

    # Attempting to run migration on protected DB must raise PermissionError
    with pytest.raises(PermissionError) as exc_mig:
        svc.apply_additive_migration()
    assert "Cannot apply migrations to protected historical database" in str(exc_mig.value)

    # Attempting to update report status on protected DB must raise PermissionError
    with pytest.raises(PermissionError) as exc_upd:
        svc.update_report_status("some-id", "verified", None, user)
    assert "Cannot update report status in protected historical database" in str(exc_upd.value)

    # Attempting to assign report on protected DB must raise PermissionError
    with pytest.raises(PermissionError) as exc_asg:
        svc.assign_report("some-id", 2, "patrol assigned", user)
    assert "Cannot assign reports in protected historical database" in str(exc_asg.value)

    # Fail-closed guard verification
    from src.services.report_service import _is_protected_db
    assert _is_protected_db(None) is True
    assert _is_protected_db("") is True
    assert _is_protected_db(Path("data/routewise_local.db")) is True

    sha_after = compute_hash()
    assert sha_before == sha_after, "Protected historical database hash must remain byte-identical"


# ==============================================================================
# Part E: Section 3 Category API-Level & Integration Tests
# ==============================================================================

def test_event_with_unmapped_hazard_type_api_endpoints(isolated_services, set_live_mode, monkeypatch):
    """API endpoints (events, alerts, journey) serialize successfully and do not crash with unmapped hazard types."""
    set_live_mode("live")
    hazard_svc = isolated_services["hazard_svc"]
    all_segs = isolated_services["all_segs"]
    seg = all_segs[0]

    now_iso = datetime.now(timezone.utc).isoformat()
    exp_iso = (datetime.now(timezone.utc) + timedelta(hours=24)).isoformat()
    ev_id = str(uuid.uuid4())

    with sqlite3.connect(isolated_services["db_path"]) as conn:
        conn.execute(
            """
            INSERT INTO hazard_event (
                id, segment_id, hazard_type, severity, status, origin,
                is_simulated, source_report_id, report_count, last_reported_at,
                starts_at, expires_at, created_by, created_at
            ) VALUES (?, ?, 'wildlife_crossing', 'medium', 'active', 'field_report', 0, NULL, 1, ?, ?, ?, 1, ?)
            """,
            (ev_id, seg, now_iso, now_iso, exp_iso, now_iso),
        )
        conn.commit()

    hazard_svc.invalidate_cache()

    from src.api.app import app
    import src.api.routes.events as ev_mod
    monkeypatch.setattr(ev_mod, "hazard_event_service", hazard_svc)

    client = TestClient(app)

    # 1. /api/v1/events/active
    r_events = client.get("/api/v1/events/active")
    assert r_events.status_code == 200
    events_data = r_events.json()
    assert any(e["hazard_type"] == "wildlife_crossing" for e in events_data)

    # 2. /api/v1/alerts/active
    r_alerts = client.get("/api/v1/alerts/active")
    assert r_alerts.status_code == 200

    # 3. /api/v1/journey/plan
    r_plan = client.post(
        "/api/v1/journey/plan",
        json={
            "origin": "Ramban Gateway",
            "destination": "Banihal Gateway",
            "mode": "live",
            "date": "2026-11-10",
        },
    )
    assert r_plan.status_code == 200


def test_create_report_integration_unmapped_categories_separate_events(isolated_services):
    """Integration test through ReportService.create_report():
    1. Preset categories ('landslide', 'flooding', and 'road_damage') on the same segment create separate hazard events.
    2. Non-preset category ('other') falls back to 'road_damage' and links to the active road-damage event as a duplicate.
    3. Each report remains independently stored.
    4. Resulting event links and deduplication references are correct.
    """
    report_svc = isolated_services["report_svc"]
    all_segs = isolated_services["all_segs"]
    seg = all_segs[0]

    from src.api.schemas.auth import UserProfile, UserRole
    from src.api.schemas.reports import ReportStatusUpdateRequest, ReportStatus
    user1 = UserProfile(id=1, email="u1@test.com", name="User 1", role=UserRole.USER.value, preferred_vehicle="Car", created_at="2026-11-10T00:00:00Z")
    user2 = UserProfile(id=2, email="u2@test.com", name="User 2", role=UserRole.USER.value, preferred_vehicle="Car", created_at="2026-11-10T00:00:00Z")
    user3 = UserProfile(id=3, email="u3@test.com", name="User 3", role=UserRole.USER.value, preferred_vehicle="Car", created_at="2026-11-10T00:00:00Z")
    patrol = UserProfile(id=3, email="p@test.com", name="Officer Singh", role=UserRole.PATROL.value, preferred_vehicle="Car", created_at="2026-11-10T00:00:00Z")

    with sqlite3.connect(isolated_services["db_path"]) as conn:
        coords = conn.execute("SELECT latitude, longitude FROM reports WHERE nearest_segment_id = ? LIMIT 1", (seg,)).fetchone()
    lat = coords[0] if coords else 33.24
    lon = coords[1] if coords else 75.24

    # 1. Submit Report 1: category 'landslide'
    rep1 = report_svc.create_report(
        client_uuid=str(uuid.uuid4()),
        category="landslide",
        description="Massive landslide",
        latitude=lat,
        longitude=lon,
        client_created_at=None,
        photo=None,
        reporter=user1,
    )
    report_svc.update_report_status(
        report_id=rep1.id,
        new_status="verified",
        note=None,
        actor=patrol,
    )

    # 2. Submit Report 2: category 'flooding'
    rep2 = report_svc.create_report(
        client_uuid=str(uuid.uuid4()),
        category="flooding",
        description="Flash flood across road",
        latitude=lat,
        longitude=lon,
        client_created_at=None,
        photo=None,
        reporter=user2,
    )
    report_svc.update_report_status(
        report_id=rep2.id,
        new_status="verified",
        note=None,
        actor=patrol,
    )

    # 3. Submit Report 3: category 'road_damage'
    rep3 = report_svc.create_report(
        client_uuid=str(uuid.uuid4()),
        category="road_damage",
        description="Potholes and fissures",
        latitude=lat,
        longitude=lon,
        client_created_at=None,
        photo=None,
        reporter=user3,
    )
    report_svc.update_report_status(
        report_id=rep3.id,
        new_status="verified",
        note=None,
        actor=patrol,
    )

    r1 = report_svc.get_report_by_id(rep1.id, patrol)
    r2 = report_svc.get_report_by_id(rep2.id, patrol)
    r3 = report_svc.get_report_by_id(rep3.id, patrol)

    # All three reports must be independently stored
    assert r1.id != r2.id != r3.id

    # None must be marked as duplicate_of another
    assert r1.duplicate_of is None
    assert r2.duplicate_of is None
    assert r3.duplicate_of is None

    # Each must link to its own separate event
    assert r1.hazard_event_id is not None
    assert r2.hazard_event_id is not None
    assert r3.hazard_event_id is not None
    assert r1.hazard_event_id != r2.hazard_event_id
    assert r1.hazard_event_id != r3.hazard_event_id
    assert r2.hazard_event_id != r3.hazard_event_id

    # Verify event hazard types in DB
    with sqlite3.connect(isolated_services["db_path"]) as conn:
        ev1 = conn.execute("SELECT hazard_type FROM hazard_event WHERE id = ?", (r1.hazard_event_id,)).fetchone()
        ev2 = conn.execute("SELECT hazard_type FROM hazard_event WHERE id = ?", (r2.hazard_event_id,)).fetchone()
        ev3 = conn.execute("SELECT hazard_type FROM hazard_event WHERE id = ?", (r3.hazard_event_id,)).fetchone()

    assert ev1[0] == "landslide"
    assert ev2[0] == "flooding"
    assert ev3[0] == "road_damage"

    # 4. Report 4 with non-preset category 'other': falls back to 'road_damage' in dedup & event creation
    user4 = UserProfile(id=4, email="u4@test.com", name="User 4", role=UserRole.USER.value, preferred_vehicle="Car", created_at="2026-11-10T00:00:00Z")
    rep4 = report_svc.create_report(
        client_uuid=str(uuid.uuid4()),
        category="other",
        description="Fallen obstacle",
        latitude=lat,
        longitude=lon,
        client_created_at=None,
        photo=None,
        reporter=user4,
    )
    r4 = report_svc.get_report_by_id(rep4.id, patrol)
    assert r4.id != rep3.id
    assert r4.duplicate_of == rep3.id
    assert r4.hazard_event_id == r3.hazard_event_id


# ==============================================================================
# Part F: Section 4(b) Verified Corroboration & last_reported_at Tests
# ==============================================================================

def test_unverified_duplicate_does_not_bump_last_reported_at_or_extend_window(isolated_services):
    """An unverified duplicate report:
    1. is stored and linked correctly (duplicate_of and hazard_event_id);
    2. does not change last_reported_at on the hazard event;
    3. does not extend the deduplication / expiry window;
    4. does not inflate report_count.
    Assignment alone does not update last_reported_at.
    Only explicit verification updates last_reported_at, report_count and extends expiry.
    """
    report_svc = isolated_services["report_svc"]
    all_segs = isolated_services["all_segs"]
    seg = all_segs[0]

    from src.api.schemas.auth import UserProfile, UserRole
    from src.api.schemas.reports import ReportStatusUpdateRequest, ReportAssignRequest, ReportStatus
    user1 = UserProfile(id=1, email="u1@test.com", name="User 1", role=UserRole.USER.value, preferred_vehicle="Car", created_at="2026-11-10T00:00:00Z")
    user2 = UserProfile(id=2, email="u2@test.com", name="User 2", role=UserRole.USER.value, preferred_vehicle="Car", created_at="2026-11-10T00:00:00Z")
    patrol = UserProfile(id=3, email="p@test.com", name="Officer Singh", role=UserRole.PATROL.value, preferred_vehicle="Car", created_at="2026-11-10T00:00:00Z")

    with sqlite3.connect(isolated_services["db_path"]) as conn:
        coords = conn.execute("SELECT latitude, longitude FROM reports WHERE nearest_segment_id = ? LIMIT 1", (seg,)).fetchone()
    lat = coords[0] if coords else 33.24
    lon = coords[1] if coords else 75.24

    # 1. Primary Report: created and verified
    rep1 = report_svc.create_report(
        client_uuid=str(uuid.uuid4()),
        category="landslide",
        description="Massive landslide blocking both lanes",
        latitude=lat,
        longitude=lon,
        client_created_at=None,
        photo=None,
        reporter=user1,
    )
    report_svc.update_report_status(
        report_id=rep1.id,
        new_status="verified",
        note=None,
        actor=patrol,
    )

    r1 = report_svc.get_report_by_id(rep1.id, patrol)
    ev_id = r1.hazard_event_id
    assert ev_id is not None

    with sqlite3.connect(isolated_services["db_path"]) as conn:
        ev_initial = conn.execute(
            "SELECT report_count, last_reported_at, expires_at FROM hazard_event WHERE id = ?",
            (ev_id,),
        ).fetchone()

    initial_count = ev_initial[0]
    initial_last_rep = ev_initial[1]
    initial_expires = ev_initial[2]
    assert initial_count == 1
    assert initial_last_rep is not None

    # 2. Duplicate submission by User 2: unverified (status='submitted')
    rep2 = report_svc.create_report(
        client_uuid=str(uuid.uuid4()),
        category="landslide",
        description="Still blocked by same landslide",
        latitude=lat,
        longitude=lon,
        client_created_at=None,
        photo=None,
        reporter=user2,
    )
    r2 = report_svc.get_report_by_id(rep2.id, patrol)

    # 1. Stored and linked correctly
    assert r2.status == "submitted"
    assert r2.hazard_event_id == ev_id
    assert r2.duplicate_of == rep1.id

    # Check hazard_event table: must NOT have been changed by unverified submission
    with sqlite3.connect(isolated_services["db_path"]) as conn:
        ev_after_submit = conn.execute(
            "SELECT report_count, last_reported_at, expires_at FROM hazard_event WHERE id = ?",
            (ev_id,),
        ).fetchone()

    # 2. Does not change last_reported_at
    assert ev_after_submit[1] == initial_last_rep
    # 3. Does not extend window / expires_at
    assert ev_after_submit[2] == initial_expires
    # 4. Does not inflate report_count
    assert ev_after_submit[0] == initial_count

    # 3. Now assign report 2 directly to patrol: assignment alone must not update last_reported_at
    report_svc.assign_report(
        report_id=rep1.id,
        assignee_id=3,
        note="Patrol assigned to check",
        actor=patrol,
    )

    with sqlite3.connect(isolated_services["db_path"]) as conn:
        ev_after_assign = conn.execute(
            "SELECT report_count, last_reported_at, expires_at FROM hazard_event WHERE id = ?",
            (ev_id,),
        ).fetchone()
    assert ev_after_assign[1] == initial_last_rep, "Assignment alone must not update last_reported_at"

    # 4. Now verify report 2: verification corroboration occurs
    report_svc.update_report_status(
        report_id=rep2.id,
        new_status="verified",
        note=None,
        actor=patrol,
    )

    with sqlite3.connect(isolated_services["db_path"]) as conn:
        ev_after_verify = conn.execute(
            "SELECT report_count, last_reported_at, expires_at FROM hazard_event WHERE id = ?",
            (ev_id,),
        ).fetchone()

    assert ev_after_verify[0] == 2, "Verified independent report must increment report_count"
    assert ev_after_verify[1] is not None
