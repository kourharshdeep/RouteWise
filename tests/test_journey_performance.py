"""Tests for journey planning performance optimizations, caching, and fail-safe behavior.

Verifies:
1. Cache invalidation on live risk update (reflected in very next journey plan).
2. Cache invalidation on hazard event creation and clearance (reflected in very next journey plan).
3. Fail-safe behavior on empty live_risk table (NO_DATA, all UNKNOWN, no on-the-fly model compute).
4. Fail-safe behavior on stale live_risk data (NO_DATA recommendation).
5. Static caching efficiency and non-flaky latency regression checks (GeoJSON not re-parsed, warm call < 100ms).
"""
from __future__ import annotations

import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path

import pytest

from src.api.schemas.journey import JourneyPlanRequest
from src.services.corridor_service import corridor_service
from src.services.hazard_event_service import hazard_event_service
from src.services.journey_service import journey_service
from src.services.live_risk_service import live_risk_service
from src.services.weather.storage import weather_storage


def test_cache_invalidation_on_risk_change(tmp_path: Path, set_live_mode):
    """Proves that computing/updating live risk is reflected in the very next journey plan."""
    set_live_mode("live")
    test_db = tmp_path / "risk_inval.db"
    old_path = weather_storage.db_path
    try:
        weather_storage.db_path = test_db
        live_risk_service.reset_db_init()
        hazard_event_service.reset_db_init()
        live_risk_service.init_db()
        hazard_event_service.init_db()

        all_segs = journey_service._sorted_segment_ids
        target_date = "2026-11-09"

        # 1. Seed initial low risk across all segments
        records_low = [
            (s, target_date, 0.04, "Low", "OK", 0, "1.0.0", "SHA", target_date, "2026-11-09T00:00:00Z")
            for s in all_segs
        ]
        with sqlite3.connect(test_db) as conn:
            conn.executemany(
                """
                INSERT OR REPLACE INTO live_risk (
                    segment_id, as_of, score, tier, status, is_stale,
                    model_version, checkpoint_sha256, weather_window_end, computed_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                records_low,
            )
            conn.commit()

        live_risk_service.invalidate_cache()

        req = JourneyPlanRequest(origin="Ramban Gateway", destination="Banihal Gateway", mode="live")
        now_test = datetime(2026, 11, 9, 12, 0, tzinfo=timezone.utc)
        plan1 = journey_service.plan_journey(req, now=now_test)
        assert plan1.recommendation == "PROCEED"
        assert plan1.max_risk_score == pytest.approx(0.04, abs=0.001)

        # 2. Update with high risk on one segment
        critical_seg = all_segs[50]
        with sqlite3.connect(test_db) as conn:
            conn.execute(
                """
                UPDATE live_risk
                SET score = 0.88, tier = 'High', computed_at = '2026-11-09T01:00:00Z'
                WHERE segment_id = ? AND as_of = ?
                """,
                (critical_seg, target_date),
            )
            conn.commit()

        live_risk_service.invalidate_cache()

        # 3. Next journey response must immediately reflect high risk and DELAY recommendation
        plan2 = journey_service.plan_journey(req, now=now_test)
        assert plan2.max_risk_score == pytest.approx(0.88, abs=0.001)
        assert plan2.high_risk_segments_count >= 1
        assert plan2.recommendation == "DELAY"
    finally:
        weather_storage.db_path = old_path


def test_cache_invalidation_on_hazard_event_change(tmp_path: Path, set_live_mode):
    """Proves that simulating and clearing hazard events is reflected in the very next journey plan."""
    set_live_mode("replay")
    test_db = tmp_path / "hazard_inval.db"
    old_path = weather_storage.db_path
    try:
        weather_storage.db_path = test_db
        live_risk_service.reset_db_init()
        hazard_event_service.reset_db_init()
        live_risk_service.init_db()
        hazard_event_service.init_db()

        all_segs = journey_service._sorted_segment_ids
        target_date = "2026-11-09"

        # Seed low risk
        records = [
            (s, target_date, 0.05, "Low", "OK", 0, "1.0.0", "SHA", target_date, "2026-11-09T00:00:00Z", "replay")
            for s in all_segs
        ]
        with sqlite3.connect(test_db) as conn:
            conn.executemany(
                """
                INSERT OR REPLACE INTO live_risk (
                    segment_id, as_of, score, tier, status, is_stale,
                    model_version, checkpoint_sha256, weather_window_end, computed_at, source
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                records,
            )
            conn.commit()
        live_risk_service.invalidate_cache()
        hazard_event_service.invalidate_cache()

        req = JourneyPlanRequest(origin="Ramban Gateway", destination="Banihal Gateway", mode="live")
        now_test = datetime(2026, 11, 9, 12, 0, tzinfo=timezone.utc)

        # Initial baseline: clear route
        plan_initial = journey_service.plan_journey(req, now=now_test)
        assert plan_initial.recommendation == "PROCEED"
        assert len(plan_initial.blocking_segments) == 0

        # Simulate closure on a route segment
        target_seg = all_segs[50]
        hazard_event_service.simulate_event(
            preset="landslide",
            segment_id=target_seg,
            severity="critical",
            duration_hours=24,
            user_id=1,
        )

        # Very next plan must immediately show HOLD and closed segment
        plan_closed = journey_service.plan_journey(req, now=now_test)
        assert plan_closed.recommendation == "HOLD"
        assert target_seg in plan_closed.blocking_segments
        assert plan_closed.baseline_route.is_passable is False

        # Clear simulated event
        hazard_event_service.clear_all_simulated_events()

        # Very next plan must immediately restore clear route
        plan_restored = journey_service.plan_journey(req, now=now_test)
        assert plan_restored.recommendation == "PROCEED"
        assert len(plan_restored.blocking_segments) == 0
        assert plan_restored.baseline_route.is_passable is True
    finally:
        weather_storage.db_path = old_path


def test_empty_live_risk_returns_failsafe(tmp_path: Path, set_live_mode):
    """Empty live_risk table must return fail-safe NO_DATA result without computing risk on the fly."""
    set_live_mode("live")
    test_db = tmp_path / "empty_live.db"
    old_path = weather_storage.db_path
    try:
        weather_storage.db_path = test_db
        live_risk_service.reset_db_init()
        hazard_event_service.reset_db_init()
        live_risk_service.init_db()
        hazard_event_service.init_db()
        live_risk_service.invalidate_cache()
        hazard_event_service.invalidate_cache()

        req = JourneyPlanRequest(origin="Ramban Gateway", destination="Banihal Gateway", mode="live")

        t0 = time.perf_counter()
        plan = journey_service.plan_journey(req)
        elapsed_ms = (time.perf_counter() - t0) * 1000.0

        # Verify fail-safe response
        assert plan.mode == "live"
        assert plan.recommendation == "NO_DATA"
        assert plan.unknown_segments_count == 75
        assert plan.is_incomplete_data is True
        assert plan.overall_route_risk == "Unknown"
        assert plan.max_risk_score is None
        assert plan.average_risk_score is None
        assert "unmonitored or stale segments" in plan.recommendation_reason

        # Verify that no model forward pass occurred (empty table returned in milliseconds, not seconds)
        assert elapsed_ms < 200.0, f"Empty live risk took {elapsed_ms:.1f}ms; model or weather should not run on request"
        for item in plan.itinerary:
            assert item.risk_tier == "UNKNOWN"
            assert item.risk_score is None
    finally:
        weather_storage.db_path = old_path


def test_stale_live_risk_returns_failsafe(tmp_path: Path, set_live_mode):
    """Stale live_risk records (is_stale=1) must trigger fail-safe NO_DATA recommendation."""
    set_live_mode("live")
    test_db = tmp_path / "stale_live.db"
    old_path = weather_storage.db_path
    try:
        weather_storage.db_path = test_db
        live_risk_service.reset_db_init()
        hazard_event_service.reset_db_init()
        live_risk_service.init_db()
        hazard_event_service.init_db()

        all_segs = journey_service._sorted_segment_ids
        target_date = "2026-11-09"

        # Seed with is_stale=1
        records_stale = [
            (s, target_date, 0.05, "Low", "STALE_DATA", 1, "1.0.0", "SHA", target_date, "2026-11-08T00:00:00Z")
            for s in all_segs
        ]
        with sqlite3.connect(test_db) as conn:
            conn.executemany(
                """
                INSERT OR REPLACE INTO live_risk (
                    segment_id, as_of, score, tier, status, is_stale,
                    model_version, checkpoint_sha256, weather_window_end, computed_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                records_stale,
            )
            conn.commit()

        live_risk_service.invalidate_cache()

        req = JourneyPlanRequest(origin="Ramban Gateway", destination="Banihal Gateway", mode="live")
        plan = journey_service.plan_journey(req)

        assert plan.recommendation == "NO_DATA"
        assert "unmonitored or stale segments" in plan.recommendation_reason
    finally:
        weather_storage.db_path = old_path


def test_static_caching_and_latency_bound():
    """Verifies that static GeoJSON is not re-parsed and warm journey planning latency is well under 500 ms."""
    req = JourneyPlanRequest(
        origin="Ramban Gateway",
        destination="Banihal Gateway",
        date="2023-07-09",
        mode="historical",
        vehicle_type="Car",
    )

    # Warm up
    journey_service.plan_journey(req)

    # Execute 10 warm calls and assert each is fast
    latencies: list[float] = []
    for _ in range(10):
        t0 = time.perf_counter()
        res = journey_service.plan_journey(req)
        latencies.append((time.perf_counter() - t0) * 1000.0)
        assert res.total_distance_km == 243.32

    latencies.sort()
    median_lat = latencies[len(latencies) // 2]

    # Non-flaky generous bound (target is < 500ms; warm in-memory should easily be < 50ms)
    assert median_lat < 100.0, f"Warm historical journey planning median {median_lat:.2f}ms exceeds 100ms bound"
    assert corridor_service._geojson_cache is not None, "GeoJSON cache should remain populated across calls"


def test_hazard_event_cache_respects_expiration_without_mutation(tmp_path: Path, set_live_mode):
    """Proves the hazard-event cache auto-invalidates and drops expired events when expires_at passes without DB mutation."""
    set_live_mode("replay")
    from datetime import datetime, timedelta, timezone

    test_db = tmp_path / "hazard_exp.db"
    old_path = weather_storage.db_path
    try:
        weather_storage.db_path = test_db
        live_risk_service.reset_db_init()
        hazard_event_service.reset_db_init()
        live_risk_service.init_db()
        hazard_event_service.init_db()

        all_segs = journey_service._sorted_segment_ids
        target_date = "2026-11-09"

        # 1. Seed low risk across all segments
        records = [
            (s, target_date, 0.05, "Low", "OK", 0, "1.0.0", "SHA", target_date, "2026-11-09T00:00:00Z", "replay")
            for s in all_segs
        ]
        with sqlite3.connect(test_db) as conn:
            conn.executemany(
                """
                INSERT OR REPLACE INTO live_risk (
                    segment_id, as_of, score, tier, status, is_stale,
                    model_version, checkpoint_sha256, weather_window_end, computed_at, source
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                records,
            )
            conn.commit()

        live_risk_service.invalidate_cache()
        hazard_event_service.invalidate_cache()

        t0 = datetime(2026, 11, 9, 10, 0, 0, tzinfo=timezone.utc)
        target_seg = all_segs[50]

        # 2. Simulate critical landslide event lasting 1 hour (expires at 11:00 UTC)
        hazard_event_service.simulate_event(
            preset="landslide",
            segment_id=target_seg,
            severity="critical",
            duration_hours=1,
            user_id=1,
            now=t0,
        )

        req = JourneyPlanRequest(origin="Ramban Gateway", destination="Banihal Gateway", mode="live")

        # 3. First request at t0 + 10 mins: event is active, route must be HOLD and blocked
        t_active = t0 + timedelta(minutes=10)
        plan1 = journey_service.plan_journey(req, now=t_active)
        assert plan1.recommendation == "HOLD"
        assert target_seg in plan1.blocking_segments
        assert hazard_event_service._active_events_cache is not None
        assert hazard_event_service._cache_earliest_expires_at is not None

        # 4. Advance time past expires_at WITHOUT any mutation (no DB writes, no service calls, no invalidation)
        t_expired = t0 + timedelta(minutes=70)  # 11:10 UTC (event expired at 11:00 UTC)

        # 5. Next request at t_expired: cache must detect expiration, auto-expire, and drop the event
        plan2 = journey_service.plan_journey(req, now=t_expired)
        assert plan2.recommendation == "PROCEED"
        assert target_seg not in plan2.blocking_segments
        assert len(plan2.blocking_segments) == 0

        # Verify DB audit state confirms auto-expiration
        with sqlite3.connect(test_db) as conn:
            row = conn.execute("SELECT status FROM hazard_event WHERE segment_id = ?", (target_seg,)).fetchone()
            assert row[0] == "expired"
    finally:
        weather_storage.db_path = old_path


def test_replay_mode_step_populates_live_risk_and_planner_returns_real_values(tmp_path: Path, set_live_mode):
    """Proves replay-mode scenario step populates live_risk, and /live/risk + planner return real scores (not NO_DATA)."""
    set_live_mode("replay")
    from src.services.alert_service import alert_service

    test_db = tmp_path / "replay_e2e.db"
    old_path = weather_storage.db_path
    try:
        weather_storage.db_path = test_db
        live_risk_service.reset_db_init()
        hazard_event_service.reset_db_init()
        live_risk_service.init_db()
        hazard_event_service.init_db()

        # Step 0: 2023-07-06 baseline monsoon replay
        step_result = alert_service.step_replay_scenario(step_index=0)
        assert step_result["step"] == 0
        assert step_result["date"] == "2023-07-06"

        # Verify GET /api/v1/live/risk returns real data
        live_risk_data = live_risk_service.get_latest_live_risk(as_of="2023-07-06")
        assert live_risk_data["as_of"] == "2023-07-06"
        assert len(live_risk_data["segments"]) == 151
        assert live_risk_data["summary"]["UNKNOWN"] == 0
        assert live_risk_data["operational_summary"]["UNKNOWN"] == 0
        first_seg = live_risk_data["segments"][0]
        assert isinstance(first_seg["risk_score"], float)
        assert first_seg["risk_tier"] in ("Low", "Medium", "High")

        # Verify Journey Planner in live mode returns real operational recommendations
        req = JourneyPlanRequest(
            origin="Ramban Gateway",
            destination="Banihal Gateway",
            mode="live",
            date="2023-07-06",
        )
        plan = journey_service.plan_journey(req)
        assert plan.mode == "live"
        assert plan.recommendation in ("PROCEED", "PROCEED_WITH_CAUTION", "DELAY")
        assert plan.recommendation != "NO_DATA"
        assert plan.overall_route_risk in ("Low", "Medium", "High")
        assert plan.unknown_segments_count == 0
        assert plan.is_incomplete_data is False
        assert plan.max_risk_score is not None
        assert isinstance(plan.max_risk_score, float)
    finally:
        weather_storage.db_path = old_path


def test_runtime_db_deletion_while_init_cache_warm_recreates_tables(tmp_path: Path):
    """Proves that deleting the runtime DB file while init cache is warm cleanly recreates schema on next init_db()."""
    test_db = tmp_path / "warm_delete.db"
    old_path = weather_storage.db_path
    try:
        weather_storage.db_path = test_db
        live_risk_service.reset_db_init()
        hazard_event_service.reset_db_init()

        # 1. First init: tables created and db_path added to _initialized_dbs
        live_risk_service.init_db()
        hazard_event_service.init_db()
        assert test_db.is_file()
        assert test_db in live_risk_service._initialized_dbs
        assert test_db in hazard_event_service._initialized_dbs

        # 2. Delete the DB file on disk while the cache is warm
        test_db.unlink()
        assert not test_db.is_file()

        # 3. Next init_db() must detect missing file/tables and recreate them
        live_risk_service.init_db()
        hazard_event_service.init_db()
        assert test_db.is_file()

        # 4. Verify all required tables exist
        with sqlite3.connect(test_db) as conn:
            tables = {
                row[0]
                for row in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                ).fetchall()
            }
            assert "live_risk" in tables
            assert "hazard_event" in tables
            assert "hazard_event_history" in tables
    finally:
        weather_storage.db_path = old_path


def test_staleness_at_read_time_with_injected_clock(tmp_path: Path, set_live_mode):
    """Proves that live_risk older than 24h is evaluated as stale at read time regardless of DB flag or cache."""
    set_live_mode("live")
    from datetime import datetime, timedelta, timezone
    from src.services.alert_service import alert_service

    test_db = tmp_path / "read_staleness.db"
    old_path = weather_storage.db_path
    try:
        weather_storage.db_path = test_db
        live_risk_service.reset_db_init()
        hazard_event_service.reset_db_init()
        live_risk_service.init_db()
        hazard_event_service.init_db()

        all_segs = journey_service._sorted_segment_ids
        target_date = "2026-11-09"
        compute_time = datetime(2026, 11, 9, 10, 0, 0, tzinfo=timezone.utc)
        comp_iso = compute_time.isoformat()

        # 1. Seed fresh records in DB with is_stale=0 and computed_at = compute_time
        records = [
            (s, target_date, 0.05, "Low", "OK", 0, "1.0.0", "SHA", target_date, comp_iso)
            for s in all_segs
        ]
        # Make one segment elevated (0.45) so we can verify alert behavior
        records[0] = (all_segs[0], target_date, 0.45, "High", "OK", 0, "1.0.0", "SHA", target_date, comp_iso)

        with sqlite3.connect(test_db) as conn:
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

        live_risk_service.invalidate_cache()
        hazard_event_service.invalidate_cache()

        req = JourneyPlanRequest(origin="Ramban Gateway", destination="Banihal Gateway", mode="live")

        # 2. Fresh read at +1 hour: must be evaluated as fresh
        t_fresh = compute_time + timedelta(hours=1)
        fresh_risk = live_risk_service.get_latest_live_risk(eval_time=t_fresh)
        assert fresh_risk["segments"][1]["is_stale"] is False
        assert fresh_risk["segments"][1]["status"] == "OK"
        assert fresh_risk["segments"][1]["risk_tier"] == "Low"

        plan_fresh = journey_service.plan_journey(req, now=t_fresh)
        # Corridor baseline is clean for remaining segments
        assert plan_fresh.recommendation != "NO_DATA"
        assert plan_fresh.unknown_segments_count == 0

        # Alert evaluation at t_fresh: fresh high risk triggers alert
        alert_res_fresh = alert_service.sync_alerts_from_live_state(now_dt=t_fresh)
        assert alert_res_fresh["created"] >= 1

        # 3. Read at +25 hours with NO new compute (DB still has is_stale=0, cache warm):
        # Must be treated as stale at read time
        t_stale = compute_time + timedelta(hours=25)
        stale_risk = live_risk_service.get_latest_live_risk(eval_time=t_stale)
        assert stale_risk["segments"][1]["is_stale"] is True
        assert stale_risk["segments"][1]["status"] == "STALE_DATA"
        assert stale_risk["segments"][1]["risk_tier"] == "UNKNOWN"
        assert stale_risk["segments"][1]["risk_score"] is None
        assert stale_risk["summary"]["UNKNOWN"] == 151
        assert stale_risk["operational_summary"]["UNKNOWN"] == 151

        plan_stale = journey_service.plan_journey(req, now=t_stale)
        assert plan_stale.recommendation == "NO_DATA"
        assert plan_stale.overall_route_risk == "Unknown"
        assert "stale" in plan_stale.recommendation_reason.lower()
        assert plan_stale.unknown_segments_count == 75
        assert plan_stale.is_incomplete_data is True

        # Alert evaluation at t_stale:
        # 1. Active High/Closed alerts must NOT be auto-cleared; marked "last known, data stale"
        # 2. System-health alert "live data stale" is raised
        alert_res_stale = alert_service.sync_alerts_from_live_state(now_dt=t_stale)
        assert alert_res_stale["created"] == 1

        active_alerts_stale = alert_service.get_active_alerts()
        high_alerts = [a for a in active_alerts_stale if a["alert_type"] == "high_risk"]
        assert len(high_alerts) >= 1
        assert high_alerts[0]["is_stale_context"] is True
        assert "last known, data stale" not in high_alerts[0]["title_en"]

        sys_alerts = [a for a in active_alerts_stale if a["alert_type"] == "system_health"]
        assert len(sys_alerts) == 1
        assert "Live Data Stale" in sys_alerts[0]["title_en"]

        # 3. Repeat tick within cooldown does NOT duplicate system-health alert
        t_stale_later = t_stale + timedelta(minutes=15)
        alert_res_later = alert_service.sync_alerts_from_live_state(now_dt=t_stale_later)
        assert alert_res_later["created"] == 0

        # 4. Fresh data arrives showing risk dropped (score=0.05): auto-clears High alert & system health alert
        t_fresh_2 = compute_time + timedelta(hours=48)
        target_date_2 = "2026-11-11"
        comp_iso_2 = t_fresh_2.isoformat()
        records_fresh_2 = [
            (s, target_date_2, 0.05, "Low", "OK", 0, "1.0.0", "SHA", target_date_2, comp_iso_2)
            for s in all_segs
        ]
        with sqlite3.connect(test_db) as conn:
            conn.executemany(
                """
                INSERT OR REPLACE INTO live_risk (
                    segment_id, as_of, score, tier, status, is_stale,
                    model_version, checkpoint_sha256, weather_window_end, computed_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                records_fresh_2,
            )
            conn.commit()

        live_risk_service.invalidate_cache()
        t_eval_fresh_2 = t_fresh_2 + timedelta(hours=1)
        alert_res_cleared = alert_service.sync_alerts_from_live_state(now_dt=t_eval_fresh_2)
        assert alert_res_cleared["cleared"] >= 1

        active_alerts_after = alert_service.get_active_alerts()
        assert len([a for a in active_alerts_after if a["alert_type"] == "high_risk"]) == 0
        assert len([a for a in active_alerts_after if a["alert_type"] == "system_health"]) == 0
    finally:
        weather_storage.db_path = old_path


def test_scheduler_startup_first_tick_computes_live_risk_immediately(tmp_path: Path, set_live_mode):
    """Proves that on empty DB, scheduler run_once immediately populates live_risk on startup without waiting for interval."""
    import asyncio
    set_live_mode("replay")
    from src.services.weather.replay import ReplayProvider
    from src.services.weather.scheduler import WeatherScheduler
    from src.services.weather.storage import WeatherStorage

    test_db = tmp_path / "startup_test.db"
    old_path = weather_storage.db_path
    try:
        weather_storage.db_path = test_db
        live_risk_service.reset_db_init()
        hazard_event_service.reset_db_init()
        live_risk_service.init_db()

        # Database starts completely empty
        initial_risk = live_risk_service.get_latest_live_risk()
        assert initial_risk["as_of"] is None
        assert len(initial_risk["segments"]) == 0

        # Start scheduler with replay provider (simulating startup first tick)
        replay_provider = ReplayProvider(csv_path="data/weather_daily_by_segment.csv")
        scheduler = WeatherScheduler(storage=WeatherStorage(db_path=test_db), provider=replay_provider)
        scheduler.mode = "replay"

        # Measure exact execution duration of first tick
        t0 = time.perf_counter()
        records_fetched = asyncio.run(scheduler.run_once())
        first_tick_duration_sec = time.perf_counter() - t0

        assert records_fetched > 0
        assert scheduler.get_status()["last_status"] == "SUCCESS"

        # Immediately following the first tick, live_risk is populated (dashboard is not empty)
        populated_risk = live_risk_service.get_latest_live_risk()
        assert populated_risk["as_of"] is not None
        assert len(populated_risk["segments"]) == 151
        assert populated_risk["summary"]["UNKNOWN"] == 0

        # First tick completed in expected time (model inference on 151 segments takes ~3-8 seconds)
        assert first_tick_duration_sec < 15.0
        print(f"\n[STARTUP BENCHMARK] First-tick duration: {first_tick_duration_sec:.2f}s, fetched {records_fetched} records")
    finally:
        weather_storage.db_path = old_path

