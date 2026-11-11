"""Focused Automated Verification for Task 3: Current-Date Live Risk Experience.

Verifies:
1. Current date is selected correctly (frozen clock).
2. Current-date weather rows are retrieved correctly (latest complete day, correct source).
3. Live risk is computed from the right 7-day window and as_of.
4. Historical July 2023 queries still work and are unchanged (golden regression).
5. Historical results are never returned by live endpoints, and live results never by historical endpoints.
6. Missing current-date weather -> UNKNOWN / MISSING_DATA (never zero or Low).
7. Stale weather -> STALE_DATA / UNKNOWN.
8. Partial current day is not used as a complete day.
9. 'off' mode clear disabled state (409) and 'replay' mode labeled REPLAY.
"""
from __future__ import annotations

import contextlib
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

from src.api.app import app
from src.api.config import settings
from src.services.auth_service import auth_service
from src.services.live_risk_service import LiveRiskComputationDisabledError, LiveRiskService
from src.services.weather.base import EXPECTED_DYNAMIC_FEATURES
from src.services.weather.replay import ReplayProvider
from src.services.weather.storage import WeatherStorage

client = TestClient(app)


@pytest.fixture
def isolated_live_db(tmp_path: Path):
    """Provides an isolated temporary database for live risk and weather testing."""
    test_db = tmp_path / "test_current_date_live.db"
    storage = WeatherStorage(db_path=test_db)
    storage.init_db()
    service = LiveRiskService(storage=storage)
    service.init_db()
    return storage, service


def test_current_date_selection_with_frozen_clock(isolated_live_db, set_live_mode):
    """1. Current date is selected correctly when evaluating with a frozen clock."""
    set_live_mode("live")
    storage, service = isolated_live_db
    frozen_now = datetime(2026, 11, 9, 14, 30, 0, tzinfo=timezone.utc)

    # Seed 14 days of observations ending yesterday (2026-11-08)
    provider = ReplayProvider(csv_path="data/weather_daily_by_segment.csv")
    df = provider.fetch(start_date="2024-07-01", end_date="2024-07-14")
    # Remap dates to 2026-10-26 .. 2026-11-08
    date_mapping = {
        d: (date(2026, 10, 26) + timedelta(days=i)).isoformat()
        for i, d in enumerate(sorted(df["obs_date"].unique()))
    }
    df["obs_date"] = df["obs_date"].map(date_mapping)
    df["source"] = "open-meteo"
    storage.upsert_observations(df)

    preds = service.compute_live_risk(eval_time=frozen_now, source="open-meteo")
    assert len(preds) == 151
    # as_of must be today (2026-11-09); window end must be yesterday (2026-11-08)
    assert preds[0]["as_of"] == "2026-11-09"
    assert preds[0]["weather_window_end"] == "2026-11-08"


def test_current_date_weather_rows_retrieval_and_source(isolated_live_db, set_live_mode):
    """2. Weather rows are retrieved strictly for the latest complete day and correct source."""
    set_live_mode("live")
    storage, _ = isolated_live_db

    # Seed open-meteo rows and replay rows with identical dates
    provider = ReplayProvider(csv_path="data/weather_daily_by_segment.csv")
    df_om = provider.fetch(start_date="2024-07-01", end_date="2024-07-07")
    df_om["source"] = "open-meteo"
    df_om["obs_date"] = "2026-11-08"
    storage.upsert_observations(df_om)

    df_rep = provider.fetch(start_date="2024-07-01", end_date="2024-07-07")
    df_rep["source"] = "replay"
    df_rep["obs_date"] = "2026-11-08"
    storage.upsert_observations(df_rep)

    # Retrieval for open-meteo must return only open-meteo rows
    retrieved_om = storage.get_observations(start_date="2026-11-08", end_date="2026-11-08", source="open-meteo")
    assert not retrieved_om.empty
    assert (retrieved_om["source"] == "open-meteo").all()
    assert (retrieved_om["source"] != "replay").all()


def test_live_risk_computed_from_right_window_and_as_of(isolated_live_db, set_live_mode):
    """3. Live risk is computed from the right 7-day window and advisory as_of."""
    set_live_mode("live")
    storage, service = isolated_live_db

    frozen_eval = datetime(2026, 11, 9, 12, 0, 0, tzinfo=timezone.utc)
    provider = ReplayProvider(csv_path="data/weather_daily_by_segment.csv")
    # Complete 7-day window: 2026-11-02 to 2026-11-08 (yesterday)
    df = provider.fetch(start_date="2024-07-01", end_date="2024-07-07")
    date_map = {
        d: (date(2026, 11, 2) + timedelta(days=i)).isoformat()
        for i, d in enumerate(sorted(df["obs_date"].unique()))
    }
    df["obs_date"] = df["obs_date"].map(date_map)
    df["source"] = "open-meteo"
    storage.upsert_observations(df)

    preds = service.compute_live_risk(eval_time=frozen_eval, source="open-meteo")
    assert len(preds) == 151
    for p in preds:
        assert p["as_of"] == "2026-11-09"
        assert p["weather_window_end"] == "2026-11-08"
        assert p["status"] == "OK"
        assert p["risk_tier"] in ("Low", "Medium", "High")

    # Verify runtime DB record
    with storage._get_connection() as conn:
        rows = conn.execute("SELECT as_of, weather_window_end FROM live_risk WHERE as_of='2026-11-09'").fetchall()
        assert len(rows) == 151
        assert rows[0]["weather_window_end"] == "2026-11-08"


def test_historical_july_2023_queries_unchanged():
    """4. Historical July 2023 queries still work and remain 100% unchanged."""
    resp = client.get("/api/v1/risk?date=2023-07-09")
    assert resp.status_code == 200
    data = resp.json()
    assert data["metadata"]["requested_date"] == "2023-07-09"
    assert data["metadata"]["is_live_operational_forecast"] is False
    assert data["metadata"]["dataset_type"] == "retrospective_historical_backtest"
    # Golden verification numbers
    assert data["summary"]["low_risk_count"] == 25
    assert data["summary"]["medium_risk_count"] == 50
    assert data["summary"]["high_risk_count"] == 76
    assert data["summary"]["unknown_count"] == 0


def test_mutual_exclusion_live_vs_historical_endpoints(isolated_live_db, set_live_mode, monkeypatch):
    """5. Historical results are never returned by live endpoints, and live by historical."""
    set_live_mode("live")
    storage, service = isolated_live_db
    monkeypatch.setattr("src.services.live_risk_service.live_risk_service", service)

    # 1. Historical endpoint with a live/current date returns error (not found in historical cache)
    resp_hist = client.get("/api/v1/risk?date=2026-11-09")
    assert resp_hist.status_code in (404, 400), "Historical endpoint must not serve future/live dates"

    # 2. Live endpoint returns live schema, never historical schema
    resp_live = client.get("/api/v1/live/risk")
    assert resp_live.status_code == 200
    live_data = resp_live.json()
    assert live_data["experimental"] is True
    assert "disclaimer" in live_data
    assert "Experimental" in live_data["disclaimer"]


def test_missing_current_date_weather_evaluates_unknown_never_low(isolated_live_db, set_live_mode):
    """6. Incomplete weather (<7 days) evaluates to MISSING_DATA and UNKNOWN (never zero or Low)."""
    set_live_mode("live")
    storage, service = isolated_live_db
    frozen_eval = datetime(2026, 11, 9, 12, 0, 0, tzinfo=timezone.utc)

    # Seed only 3 days of observations (less than required 7 days)
    provider = ReplayProvider(csv_path="data/weather_daily_by_segment.csv")
    df = provider.fetch(start_date="2024-07-01", end_date="2024-07-03")
    df["obs_date"] = ["2026-11-06", "2026-11-07", "2026-11-08"] * (len(df) // 3)
    df["source"] = "open-meteo"
    storage.upsert_observations(df)

    preds = service.compute_live_risk(eval_time=frozen_eval, source="open-meteo")
    assert len(preds) == 151
    for p in preds:
        assert p["status"] == "MISSING_DATA"
        assert p["risk_tier"] == "UNKNOWN"
        assert p["risk_score"] is None, "Missing weather must NEVER default to 0.0 or Low!"


def test_stale_weather_evaluates_stale_data_unknown(isolated_live_db, set_live_mode):
    """7. Telemetry older than 24 hours evaluates to STALE_DATA and UNKNOWN."""
    set_live_mode("live")
    storage, service = isolated_live_db

    # Live risk computed on 2026-11-07 (window ending 2026-11-06)
    provider = ReplayProvider(csv_path="data/weather_daily_by_segment.csv")
    df = provider.fetch(start_date="2024-07-01", end_date="2024-07-07")
    date_map = {
        d: (date(2026, 10, 31) + timedelta(days=i)).isoformat()
        for i, d in enumerate(sorted(df["obs_date"].unique()))
    }
    df["obs_date"] = df["obs_date"].map(date_map)
    df["source"] = "open-meteo"
    storage.upsert_observations(df)

    comp_time = datetime(2026, 11, 7, 10, 0, 0, tzinfo=timezone.utc)
    service.compute_live_risk(eval_time=comp_time, source="open-meteo")

    # Read at 2026-11-09 (48 hours later, stale)
    read_now = datetime(2026, 11, 9, 10, 0, 0, tzinfo=timezone.utc)
    latest = service.get_latest_live_risk(eval_time=read_now)
    assert latest["summary"]["UNKNOWN"] == 151
    assert latest["summary"]["Low"] == 0
    for seg in latest["segments"]:
        assert seg["is_stale"] is True
        assert seg["status"] == "STALE_DATA"
        assert seg["risk_tier"] == "UNKNOWN"


def test_partial_current_day_not_used_as_complete_day(isolated_live_db, set_live_mode):
    """8. Partial current-day observations are excluded from the 7-day complete lookback window."""
    set_live_mode("live")
    storage, service = isolated_live_db
    frozen_eval = datetime(2026, 11, 9, 15, 0, 0, tzinfo=timezone.utc)

    # Seed complete 7-day history: 2026-11-02 through 2026-11-08 (yesterday)
    provider = ReplayProvider(csv_path="data/weather_daily_by_segment.csv")
    df_complete = provider.fetch(start_date="2024-07-01", end_date="2024-07-07")
    date_map = {
        d: (date(2026, 11, 2) + timedelta(days=i)).isoformat()
        for i, d in enumerate(sorted(df_complete["obs_date"].unique()))
    }
    df_complete["obs_date"] = df_complete["obs_date"].map(date_map)
    df_complete["source"] = "open-meteo"
    storage.upsert_observations(df_complete)

    # Also seed partial/corrupted current-day rows for 2026-11-09 (ongoing day)
    df_partial = df_complete[df_complete["obs_date"] == "2026-11-08"].copy()
    df_partial["obs_date"] = "2026-11-09"
    df_partial["precip_mm"] = None
    df_partial["quality_flag"] = "PARTIAL"
    storage.upsert_observations(df_partial)

    # Compute risk with wall-clock on 2026-11-09
    preds = service.compute_live_risk(eval_time=frozen_eval, source="open-meteo")
    assert len(preds) == 151
    # Window must end on 2026-11-08, ignoring 2026-11-09 partial rows
    assert preds[0]["weather_window_end"] == "2026-11-08"
    assert preds[0]["as_of"] == "2026-11-09"
    # Because 2026-11-02 to 2026-11-08 was complete, status must be OK, not MISSING_DATA
    assert preds[0]["status"] == "OK"
    assert preds[0]["risk_tier"] in ("Low", "Medium", "High")


def test_off_mode_disabled_state_and_replay_mode_label(set_live_mode, isolated_live_db):
    """9. off mode returns disabled state (409 on compute); replay mode returns REPLAY provider."""
    storage, service = isolated_live_db

    # 1. off mode
    set_live_mode("off")
    assert settings.live_mode == "off"
    status_off = service.get_live_status()
    assert status_off["mode"] == "off"
    assert status_off["provider"] == "none"

    with pytest.raises(LiveRiskComputationDisabledError):
        service.compute_live_risk(source=None)

    admin_token = auth_service.create_token(user_id=1, email="admin@routewise.ai", role="admin")
    resp_step = client.post(
        "/api/v1/alerts/scenario/step",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"step_index": 0},
    )
    assert resp_step.status_code == 409

    # 2. replay mode
    set_live_mode("replay")
    assert settings.live_mode == "replay"
    status_replay = service.get_live_status()
    assert status_replay["mode"] == "replay"
    assert status_replay["provider"] == "replay"


def test_staleness_threshold_boundaries_and_invalid_timestamps(isolated_live_db, set_live_mode):
    """10. Test exactly 24h (fresh), just over 24h (stale), and missing/invalid timestamps."""
    set_live_mode("live")
    storage, service = isolated_live_db

    # Seed 7 days of complete observations ending 2026-11-08
    provider = ReplayProvider(csv_path="data/weather_daily_by_segment.csv")
    df = provider.fetch(start_date="2024-07-01", end_date="2024-07-07")
    date_map = {
        d: (date(2026, 11, 2) + timedelta(days=i)).isoformat()
        for i, d in enumerate(sorted(df["obs_date"].unique()))
    }
    df["obs_date"] = df["obs_date"].map(date_map)
    df["source"] = "open-meteo"
    storage.upsert_observations(df)

    comp_time = datetime(2026, 11, 9, 10, 0, 0, tzinfo=timezone.utc)
    service.compute_live_risk(eval_time=comp_time, source="open-meteo")

    # Boundary 1: Within yesterday UTC window and within 24h compute age (e.g. 2026-11-09 23:59:59 UTC) -> FRESH
    within_day = datetime(2026, 11, 9, 23, 59, 59, tzinfo=timezone.utc)
    service.invalidate_cache()
    res_24h = service.get_latest_live_risk(eval_time=within_day)
    assert res_24h["summary"]["UNKNOWN"] == 0
    assert res_24h["segments"][0]["is_stale"] is False
    assert res_24h["segments"][0]["status"] == "OK"

    # Boundary 2: Over 24 hours (24h + 1s) after computed_at -> STALE
    over_24h = comp_time + timedelta(hours=24, seconds=1)
    service.invalidate_cache()
    res_over = service.get_latest_live_risk(eval_time=over_24h)
    assert res_over["summary"]["UNKNOWN"] == 151
    assert res_over["segments"][0]["is_stale"] is True
    assert res_over["segments"][0]["status"] == "STALE_DATA"
    assert res_over["segments"][0]["risk_tier"] == "UNKNOWN"

    # Boundary 3: Missing/empty computed_at -> STALE
    with storage._get_connection() as conn:
        conn.execute("UPDATE live_risk SET computed_at = '' WHERE as_of = '2026-11-09'")
        conn.commit()
    service.invalidate_cache()
    res_null_comp = service.get_latest_live_risk(eval_time=comp_time)
    assert res_null_comp["summary"]["UNKNOWN"] == 151
    assert res_null_comp["segments"][0]["is_stale"] is True
    assert res_null_comp["segments"][0]["status"] == "STALE_DATA"

    # Boundary 4: Invalid/corrupt computed_at string -> STALE
    with storage._get_connection() as conn:
        conn.execute("UPDATE live_risk SET computed_at = 'INVALID_TIMESTAMP' WHERE as_of = '2026-11-09'")
        conn.commit()
    service.invalidate_cache()
    res_inv_comp = service.get_latest_live_risk(eval_time=comp_time)
    assert res_inv_comp["summary"]["UNKNOWN"] == 151
    assert res_inv_comp["segments"][0]["is_stale"] is True
    assert res_inv_comp["segments"][0]["status"] == "STALE_DATA"

    # Boundary 5: Missing/empty weather_window_end -> STALE
    with storage._get_connection() as conn:
        conn.execute(
            "UPDATE live_risk SET computed_at = ?, weather_window_end = '' WHERE as_of = '2026-11-09'",
            (comp_time.isoformat(),)
        )
        conn.commit()
    service.invalidate_cache()
    res_null_win = service.get_latest_live_risk(eval_time=comp_time)
    assert res_null_win["summary"]["UNKNOWN"] == 151
    assert res_null_win["segments"][0]["is_stale"] is True
    assert res_null_win["segments"][0]["status"] == "STALE_DATA"

    # Boundary 6: Invalid/corrupt weather_window_end string -> STALE
    with storage._get_connection() as conn:
        conn.execute(
            "UPDATE live_risk SET computed_at = ?, weather_window_end = 'NOT_A_DATE' WHERE as_of = '2026-11-09'",
            (comp_time.isoformat(),)
        )
        conn.commit()
    service.invalidate_cache()
    res_inv_win = service.get_latest_live_risk(eval_time=comp_time)
    assert res_inv_win["summary"]["UNKNOWN"] == 151
    assert res_inv_win["segments"][0]["is_stale"] is True
    assert res_inv_win["segments"][0]["status"] == "STALE_DATA"


def test_utc_frozen_clocks_nov9_2130_and_nov10_0030(isolated_live_db, set_live_mode):
    """11. Item 1: Test frozen clocks at 2026-11-09 21:30 UTC (03:00 IST on 10 Nov) and 2026-11-10 00:30 UTC."""
    set_live_mode("live")
    storage, service = isolated_live_db

    # Seed 14 days of observations: 2026-10-27 through 2026-11-09
    provider = ReplayProvider(csv_path="data/weather_daily_by_segment.csv")
    df = provider.fetch(start_date="2024-07-01", end_date="2024-07-14")
    date_map = {
        d: (date(2026, 10, 27) + timedelta(days=i)).isoformat()
        for i, d in enumerate(sorted(df["obs_date"].unique()))
    }
    df["obs_date"] = df["obs_date"].map(date_map)
    df["source"] = "open-meteo"
    storage.upsert_observations(df)

    # Clock 1: 2026-11-09 21:30 UTC (which is 2026-11-10 03:00 IST)
    # UTC date is 2026-11-09, so as_of must be 2026-11-09 and weather_window_end must be 2026-11-08
    clock1 = datetime(2026, 11, 9, 21, 30, 0, tzinfo=timezone.utc)
    service.invalidate_cache()
    preds1 = service.compute_live_risk(eval_time=clock1, source="open-meteo")
    assert preds1[0]["as_of"] == "2026-11-09"
    assert preds1[0]["weather_window_end"] == "2026-11-08"

    # Clock 2: 2026-11-10 00:30 UTC
    # UTC date is 2026-11-10, so as_of must be 2026-11-10 and weather_window_end must be 2026-11-09
    clock2 = datetime(2026, 11, 10, 0, 30, 0, tzinfo=timezone.utc)
    service.invalidate_cache()
    preds2 = service.compute_live_risk(eval_time=clock2, source="open-meteo")
    assert preds2[0]["as_of"] == "2026-11-10"
    assert preds2[0]["weather_window_end"] == "2026-11-09"


def test_extreme_today_observation_row_invariance(isolated_live_db, set_live_mode):
    """12. Item 3: Seeding extreme today-dated row does not alter compute_live_risk output."""
    set_live_mode("live")
    storage, service = isolated_live_db
    eval_clock = datetime(2026, 11, 9, 14, 0, 0, tzinfo=timezone.utc)

    # Seed complete 7-day lookback window: 2026-11-02 through 2026-11-08
    provider = ReplayProvider(csv_path="data/weather_daily_by_segment.csv")
    df_clean = provider.fetch(start_date="2024-07-01", end_date="2024-07-07")
    date_map = {
        d: (date(2026, 11, 2) + timedelta(days=i)).isoformat()
        for i, d in enumerate(sorted(df_clean["obs_date"].unique()))
    }
    df_clean["obs_date"] = df_clean["obs_date"].map(date_map)
    df_clean["source"] = "open-meteo"
    storage.upsert_observations(df_clean)

    # Baseline risk computation without any today rows
    service.invalidate_cache()
    baseline_preds = service.compute_live_risk(eval_time=eval_clock, source="open-meteo")
    baseline_scores = {p["segment_id"]: p["risk_score"] for p in baseline_preds}

    # Now seed today-dated rows (2026-11-09) with extreme, catastrophic weather values
    df_extreme = df_clean[df_clean["obs_date"] == "2026-11-08"].copy()
    df_extreme["obs_date"] = "2026-11-09"
    df_extreme["precip_mm"] = 999.0
    df_extreme["snowfall_mm_we"] = 500.0
    df_extreme["temp_mean_c"] = -45.0
    storage.upsert_observations(df_extreme)

    # Re-compute risk with the exact same clock
    service.invalidate_cache()
    extreme_preds = service.compute_live_risk(eval_time=eval_clock, source="open-meteo")
    extreme_scores = {p["segment_id"]: p["risk_score"] for p in extreme_preds}

    # Must be 100% identical: today's partial/extreme observations are strictly excluded
    assert len(baseline_preds) == len(extreme_preds) == 151
    for p in extreme_preds:
        sid = p["segment_id"]
        assert p["weather_window_end"] == "2026-11-08"
        assert p["as_of"] == "2026-11-09"
        assert p["risk_score"] == baseline_scores[sid]
        assert p["status"] == "OK"


def test_staleness_midnight_boundaries_and_two_days_ago(isolated_live_db, set_live_mode):
    """13. Item 4: Test midnight boundaries (23:59:59 fresh vs 00:00:01 stale) and 2 days ago stale."""
    set_live_mode("live")
    storage, service = isolated_live_db

    # Seed 7 days ending 2026-11-08
    provider = ReplayProvider(csv_path="data/weather_daily_by_segment.csv")
    df = provider.fetch(start_date="2024-07-01", end_date="2024-07-07")
    date_map = {
        d: (date(2026, 11, 2) + timedelta(days=i)).isoformat()
        for i, d in enumerate(sorted(df["obs_date"].unique()))
    }
    df["obs_date"] = df["obs_date"].map(date_map)
    df["source"] = "open-meteo"
    storage.upsert_observations(df)

    comp_time = datetime(2026, 11, 9, 12, 0, 0, tzinfo=timezone.utc)
    service.compute_live_risk(eval_time=comp_time, source="open-meteo")

    # Boundary A: Just before UTC midnight on 2026-11-09 (23:59:59 UTC) -> window end 2026-11-08 is yesterday UTC -> FRESH
    clock_before_midnight = datetime(2026, 11, 9, 23, 59, 59, tzinfo=timezone.utc)
    service.invalidate_cache()
    res_fresh = service.get_latest_live_risk(eval_time=clock_before_midnight)
    assert res_fresh["summary"]["UNKNOWN"] == 0
    assert res_fresh["segments"][0]["is_stale"] is False
    assert res_fresh["segments"][0]["status"] == "OK"

    # Boundary B: Just after UTC midnight on 2026-11-10 (00:00:01 UTC) -> window end 2026-11-08 is now 2 days ago -> STALE
    clock_after_midnight = datetime(2026, 11, 10, 0, 0, 1, tzinfo=timezone.utc)
    service.invalidate_cache()
    res_stale = service.get_latest_live_risk(eval_time=clock_after_midnight)
    assert res_stale["summary"]["UNKNOWN"] == 151
    assert res_stale["segments"][0]["is_stale"] is True
    assert res_stale["segments"][0]["status"] == "STALE_DATA"
    assert res_stale["segments"][0]["risk_tier"] == "UNKNOWN"

    # Boundary C: 2 days ago relative to evaluation clock -> STALE
    clock_two_days_later = datetime(2026, 11, 11, 12, 0, 0, tzinfo=timezone.utc)
    service.invalidate_cache()
    res_two_days = service.get_latest_live_risk(eval_time=clock_two_days_later)
    assert res_two_days["summary"]["UNKNOWN"] == 151
    assert res_two_days["segments"][0]["is_stale"] is True
    assert res_two_days["segments"][0]["status"] == "STALE_DATA"


def test_legacy_schema_migration_and_row_preservation(tmp_path: Path):
    """14. Item 5: Legacy live_risk table without weather_window_end migrates idempotently and preserves rows."""
    legacy_db_path = tmp_path / "legacy_test.db"
    
    # 1. Create a legacy table without weather_window_end column
    import sqlite3
    with sqlite3.connect(legacy_db_path) as conn:
        conn.execute(
            """
            CREATE TABLE live_risk (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                segment_id TEXT NOT NULL,
                as_of TEXT NOT NULL,
                score REAL,
                tier TEXT NOT NULL,
                status TEXT NOT NULL,
                is_stale INTEGER NOT NULL DEFAULT 0,
                model_version TEXT NOT NULL,
                checkpoint_sha256 TEXT NOT NULL,
                computed_at TEXT NOT NULL,
                UNIQUE(segment_id, as_of)
            );
            """
        )
        conn.execute(
            """
            INSERT INTO live_risk (
                segment_id, as_of, score, tier, status, is_stale,
                model_version, checkpoint_sha256, computed_at
            ) VALUES ('seg_legacy_001', '2024-07-15', 0.12, 'Medium', 'OK', 0, '1.0.0', 'LEGACY_SHA', '2024-07-15T12:00:00Z');
            """
        )
        conn.commit()

    # 2. Initialize storage & service against legacy DB
    storage = WeatherStorage(db_path=legacy_db_path)
    service = LiveRiskService(storage=storage)
    service.init_db()

    # 3. Verify weather_window_end column exists after additive idempotent migration
    with sqlite3.connect(legacy_db_path) as conn:
        cols = [r[1] for r in conn.execute("PRAGMA table_info(live_risk);").fetchall()]
        assert "weather_window_end" in cols, "Additive migration must create weather_window_end column"

        # 4. Old legacy row must remain intact and report its own data
        row = conn.execute("SELECT segment_id, as_of, score, weather_window_end FROM live_risk WHERE segment_id='seg_legacy_001'").fetchone()
        assert row[0] == "seg_legacy_001"
        assert row[1] == "2024-07-15"
        assert row[2] == 0.12
        # Old row had NULL weather_window_end
        assert row[3] is None

    # 5. Verify service reads legacy row without crash and reports its own as_of
    service.invalidate_cache()
    res = service.get_latest_live_risk(as_of="2024-07-15")
    assert res["as_of"] == "2024-07-15"
    assert res["segments"][0]["segment_id"] == "seg_legacy_001"


def test_replay_empty_replay_table_failsafe_no_data(isolated_live_db, set_live_mode):
    """15. Replay mode with empty replay table returns explicit fail-safe NO_DATA/UNKNOWN, never falling back to today_utc."""
    set_live_mode("replay")
    storage, service = isolated_live_db

    # No replay observations seeded in storage.
    preds = service.compute_live_risk(source="replay")
    assert len(preds) == 151
    for p in preds:
        assert p["as_of"] is None
        assert p["weather_window_end"] is None
        assert p["risk_tier"] == "UNKNOWN"
        assert p["status"] == "NO_DATA"
        assert p["risk_score"] is None

    # Read-time endpoint also returns fail-safe NO_DATA/UNKNOWN
    latest = service.get_latest_live_risk()
    assert latest["as_of"] is None
    assert latest["summary"]["UNKNOWN"] == 151
    assert latest["summary"]["Low"] == 0
    assert len(latest["segments"]) == 0

    status = service.get_live_status()
    assert status["mode"] == "replay"
    assert status["latest_risk_as_of"] is None
    assert status["data_age_hours"] == 0.0


def test_source_isolation_live_vs_replay(isolated_live_db, set_live_mode):
    """16. Source isolation: live mode reads only open-meteo rows and replay mode reads only replay rows."""
    storage, service = isolated_live_db

    # Seed 7 days of open-meteo observations for 2026-11-08
    provider = ReplayProvider(csv_path="data/weather_daily_by_segment.csv")
    df_live = provider.fetch(start_date="2024-07-01", end_date="2024-07-07")
    date_mapping_live = {
        d: (date(2026, 11, 2) + timedelta(days=i)).isoformat()
        for i, d in enumerate(sorted(df_live["obs_date"].unique()))
    }
    df_live["obs_date"] = df_live["obs_date"].map(date_mapping_live)
    df_live["source"] = "open-meteo"
    storage.upsert_observations(df_live)

    # Compute live risk for open-meteo
    set_live_mode("live")
    live_eval = datetime(2026, 11, 9, 12, 0, 0, tzinfo=timezone.utc)
    service.compute_live_risk(eval_time=live_eval, source="open-meteo")

    # Seed 7 days of replay observations for 2024-07-15
    df_replay = provider.fetch(start_date="2024-07-09", end_date="2024-07-15")
    df_replay["source"] = "replay"
    storage.upsert_observations(df_replay)

    # Compute live risk for replay
    set_live_mode("replay")
    replay_eval = datetime(2024, 7, 15, 12, 0, 0, tzinfo=timezone.utc)
    service.compute_live_risk(as_of="2024-07-15", eval_time=replay_eval, source="replay")

    # In replay mode: get_latest_live_risk must return 2024-07-15 replay evaluation, not 2026-11-09 live
    service.invalidate_cache()
    rep_latest = service.get_latest_live_risk(eval_time=replay_eval)
    assert rep_latest["as_of"] == "2024-07-15"
    assert rep_latest["summary"]["Low"] > 0 or rep_latest["summary"]["Medium"] > 0
    rep_status = service.get_live_status()
    assert rep_status["latest_risk_as_of"] == "2024-07-15"
    assert rep_status["data_age_hours"] == 0.0

    # In live mode: get_latest_live_risk must return 2026-11-09 live evaluation, not 2024-07-15 replay
    set_live_mode("live")
    service.invalidate_cache()
    live_latest = service.get_latest_live_risk(eval_time=live_eval)
    assert live_latest["as_of"] == "2026-11-09"
    assert live_latest["weather_window_end"] == "2026-11-08"
    live_status = service.get_live_status()
    assert live_status["latest_risk_as_of"] == "2026-11-09"



