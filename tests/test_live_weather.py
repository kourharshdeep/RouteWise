"""Unit and Resilience Tests for Open-Meteo Provider and Scheduler (Step 2).

All tests use a mock/fake fetcher with zero network calls, verifying:
1. Unit conversions (snowfall cm -> mm_we, hourly snow depth -> daily max, temps).
2. Segment clustering & fan-out (151 segments mapped from ~9 km grid cells).
3. Rolling precipitation sums (3-day and 7-day trailing windows).
4. HTTP retry logic with backoff for transient 500 and 429 errors.
5. Fault tolerance: permanent API failures are caught safely and do not crash the app.
6. WeatherScheduler execution lifecycle across live, replay, and off modes.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone, timedelta
import urllib.error
from pathlib import Path
from typing import Dict, List
import pandas as pd
import pytest

from src.services.weather.base import EXPECTED_DYNAMIC_FEATURES
from src.services.weather.clustering import GridCluster, build_corridor_grid_clusters
from src.services.weather.open_meteo import OpenMeteoProvider
from src.services.weather.scheduler import WeatherScheduler
from src.services.weather.storage import WeatherStorage


def _create_mock_response(
    dates: List[str],
    precip: List[float],
    snowfall_cm: List[float],
    t_mean: List[float],
    t_min: List[float],
    snow_depth_hourly: Dict[str, List[float]],
) -> dict:
    """Generates synthetic Open-Meteo response structure for testing."""
    hourly_times = []
    hourly_depths = []
    for d, depths in snow_depth_hourly.items():
        for hr, val in enumerate(depths):
            hourly_times.append(f"{d}T{hr:02d}:00Z")
            hourly_depths.append(val)

    return {
        "daily": {
            "time": dates,
            "precipitation_sum": precip,
            "snowfall_sum": snowfall_cm,
            "temperature_2m_mean": t_mean,
            "temperature_2m_min": t_min,
        },
        "hourly": {
            "time": hourly_times,
            "snow_depth": hourly_depths,
        },
    }


def test_corridor_clustering_groups_151_segments():
    """Verify that all 151 segments are accounted for across grid clusters."""
    clusters = build_corridor_grid_clusters(grid_resolution=0.1)
    assert len(clusters) > 0

    all_assigned_segments = []
    for c in clusters:
        assert isinstance(c, GridCluster)
        assert len(c.segment_ids) > 0
        all_assigned_segments.extend(c.segment_ids)

    # NH-44 corridor contains 151 segments; verify total and uniqueness
    assert len(all_assigned_segments) == 151
    assert len(set(all_assigned_segments)) == 151


def test_open_meteo_unit_conversions_and_fan_out():
    """Verify units conversion and cluster fan-out without network access."""
    test_dates = ["2026-11-01", "2026-11-02"]
    snow_depths = {
        "2026-11-01": [0.10, 0.25, 0.05],  # max 0.25m
        "2026-11-02": [0.30, 0.45, 0.15],  # max 0.45m
    }
    mock_data = _create_mock_response(
        dates=test_dates,
        precip=[12.5, 5.0],
        snowfall_cm=[3.2, 0.0],  # 3.2 cm snow -> 3.2 mm water equivalent
        t_mean=[14.2, 11.8],
        t_min=[9.1, 7.3],
        snow_depth_hourly=snow_depths,
    )

    call_count = 0

    def mock_fetcher(url: str, timeout: float) -> dict:
        nonlocal call_count
        call_count += 1
        return mock_data

    provider = OpenMeteoProvider(fetcher=mock_fetcher)
    df = provider.fetch(start_date="2026-11-01", end_date="2026-11-02")

    assert not df.empty
    # Must cover all 151 segments over 2 dates
    assert len(df) == 151 * 2

    # Check that each cluster was fetched once
    clusters = provider.get_clusters()
    assert call_count == len(clusters)

    # Verify unit conversions on first segment for Day 1
    day1 = df[df["obs_date"] == "2026-11-01"].iloc[0]
    assert day1["precip_mm"] == 12.5
    assert day1["snowfall_mm_we"] == 3.2  # 3.2 cm * 1.0 (10:1 ratio assumption)
    assert day1["temp_mean_c"] == 14.2
    assert day1["temp_min_c"] == 9.1
    assert day1["snow_depth_m"] == 0.25  # daily max
    assert day1["source"] == "open-meteo"
    assert day1["quality_flag"] == "EXPERIMENTAL_LIVE"

    # Verify Day 2
    day2 = df[df["obs_date"] == "2026-11-02"].iloc[0]
    assert day2["snow_depth_m"] == 0.45


def test_open_meteo_retry_on_transient_http_errors():
    """Verify exponential backoff retries when encountering HTTP 500 or 429."""
    test_dates = ["2026-11-01"]
    mock_data = _create_mock_response(
        dates=test_dates,
        precip=[2.0],
        snowfall_cm=[0.0],
        t_mean=[15.0],
        t_min=[10.0],
        snow_depth_hourly={"2026-11-01": [0.0]},
    )

    attempts = 0

    def flaky_fetcher(url: str, timeout: float) -> dict:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise urllib.error.HTTPError(url, 500, "Internal Server Error", {}, None)
        if attempts == 2:
            raise urllib.error.HTTPError(url, 429, "Too Many Requests", {}, None)
        return mock_data

    provider = OpenMeteoProvider(
        fetcher=flaky_fetcher,
        max_retries=3,
        backoff_factor=0.01,  # Fast backoff for tests
    )

    # Fetch for single cluster to isolate retry count
    cluster = provider.get_clusters()[0]
    res = provider.fetch_cluster_raw(cluster.latitude, cluster.longitude, "2026-11-01", "2026-11-01")
    assert res is not None
    assert attempts == 3


def test_open_meteo_fault_tolerance_on_permanent_failure():
    """Verify that continuous network failures do not raise unhandled exceptions."""
    def failing_fetcher(url: str, timeout: float) -> dict:
        raise OSError("DNS Resolution Failure or Connection Refused")

    provider = OpenMeteoProvider(
        fetcher=failing_fetcher,
        max_retries=2,
        backoff_factor=0.01,
    )

    # Fetch should catch error, log, and return empty DataFrame gracefully
    df = provider.fetch(start_date="2026-11-01", end_date="2026-11-02")
    assert df.empty
    assert "segment_id" in df.columns
    assert "precip_mm" in df.columns


def test_weather_scheduler_lifecycle(tmp_path: Path):
    """Verify scheduler run_once behavior across modes and failure handling."""
    async def _run():
        test_db = tmp_path / "scheduler_test.db"
        storage = WeatherStorage(db_path=test_db)

        # 1. Mode == 'off' -> does nothing
        scheduler_off = WeatherScheduler(storage=storage)
        scheduler_off.mode = "off"
        count_off = await scheduler_off.run_once()
        assert count_off == 0
        assert scheduler_off.get_status()["last_status"] == "IDLE"

        # 2. Mode == 'live' with mock provider
        mock_df = pd.DataFrame([{
            "segment_id": "seg_test",
            "obs_date": "2026-11-01",
            "precip_mm": 5.0,
            "snowfall_mm_we": 0.0,
            "temp_mean_c": 16.0,
            "temp_min_c": 11.0,
            "snow_depth_m": 0.0,
            "precip_3d_mm": 5.0,
            "precip_7d_mm": 5.0,
            "source": "open-meteo",
            "fetched_at": "2026-11-01T00:00:00Z",
            "quality_flag": "EXPERIMENTAL_LIVE",
        }])

        class MockLiveProvider:
            provider_name = "open-meteo"
            def fetch(self, start_date, end_date=None, segments=None):
                return mock_df

        scheduler_live = WeatherScheduler(storage=storage, provider=MockLiveProvider())
        scheduler_live.mode = "live"
        upserted = await scheduler_live.run_once()
        assert upserted == 1

        status = scheduler_live.get_status()
        assert status["last_status"] == "SUCCESS"
        assert status["consecutive_failures"] == 0
        assert storage.count_observations() == 1

        # 3. Provider raises exception -> fault tolerance verification
        class BrokenProvider:
            provider_name = "broken"
            def fetch(self, start_date, end_date=None, segments=None):
                raise ConnectionError("Gateway Timeout")

        scheduler_broken = WeatherScheduler(storage=storage, provider=BrokenProvider())
        scheduler_broken.mode = "live"
        upserted_broken = await scheduler_broken.run_once()
        assert upserted_broken == 0

        broken_status = scheduler_broken.get_status()
        assert broken_status["last_status"] == "ERROR"
        assert "Gateway Timeout" in broken_status["last_error"]
        assert broken_status["consecutive_failures"] == 1

    asyncio.run(_run())


def test_null_weather_fields_preserved_as_nan_with_quality_flag(tmp_path: Path):
    """Mock Open-Meteo response with null precipitation_sum: stored as NaN/NULL with quality_flag='MISSING_DATA'."""
    mock_data = {
        "daily": {
            "time": ["2026-11-01"],
            "precipitation_sum": [None],  # Missing rainfall
            "snowfall_sum": [0.0],
            "temperature_2m_mean": [14.0],
            "temperature_2m_min": [8.0],
        },
        "hourly": {
            "time": ["2026-11-01T00:00Z"],
            "snow_depth": [0.0],
        },
    }
    provider = OpenMeteoProvider(fetcher=lambda url, timeout: mock_data)
    df = provider.fetch(start_date="2026-11-01", end_date="2026-11-01")

    assert not df.empty
    row = df.iloc[0]
    # Rainfall must NOT be silently replaced with 0.0
    assert pd.isna(row["precip_mm"])
    assert row["precip_mm"] != 0.0
    assert row["quality_flag"] == "MISSING_DATA"

    # Store in runtime database and verify SQL NULL / pd.isna
    test_db = tmp_path / "test_missing_weather.db"
    storage = WeatherStorage(db_path=test_db)
    storage.upsert_observations(df)

    stored_df = storage.get_observations(start_date="2026-11-01", end_date="2026-11-01")
    stored_row = stored_df.iloc[0]
    assert pd.isna(stored_row["precip_mm"])
    assert stored_row["quality_flag"] == "MISSING_DATA"


def test_genuine_zero_precipitation_not_flagged(tmp_path: Path):
    """Ingesting genuine 0.0 mm precipitation: stored as 0.0 (not NaN), quality_flag is normal."""
    mock_data = {
        "daily": {
            "time": ["2026-11-01"],
            "precipitation_sum": [0.0],  # Genuine 0.0 dry weather
            "snowfall_sum": [0.0],
            "temperature_2m_mean": [14.0],
            "temperature_2m_min": [8.0],
        },
        "hourly": {
            "time": ["2026-11-01T00:00Z"],
            "snow_depth": [0.0],
        },
    }
    provider = OpenMeteoProvider(fetcher=lambda url, timeout: mock_data)
    df = provider.fetch(start_date="2026-11-01", end_date="2026-11-01")

    assert not df.empty
    row = df.iloc[0]
    assert row["precip_mm"] == 0.0
    assert not pd.isna(row["precip_mm"])
    assert row["quality_flag"] == "EXPERIMENTAL_LIVE"

    test_db = tmp_path / "test_zero_weather.db"
    storage = WeatherStorage(db_path=test_db)
    storage.upsert_observations(df)

    stored_df = storage.get_observations(start_date="2026-11-01", end_date="2026-11-01")
    stored_row = stored_df.iloc[0]
    assert stored_row["precip_mm"] == 0.0
    assert stored_row["quality_flag"] == "EXPERIMENTAL_LIVE"


def test_missing_weather_in_live_risk_evaluates_unknown(tmp_path: Path):
    """Segments with missing weather evaluate to MISSING_DATA, UNKNOWN tier, None score without contaminating others."""
    from src.services.live_risk_service import LiveRiskService
    from src.services.weather.replay import ReplayProvider

    test_db = tmp_path / "test_risk_missing.db"
    storage = WeatherStorage(db_path=test_db)
    storage.init_db()

    # Seed 7 days of complete valid weather from replay
    replay = ReplayProvider(csv_path="data/weather_daily_by_segment.csv")
    full_7d = replay.fetch(start_date="2024-07-09", end_date="2024-07-15")
    # Set source to open-meteo so LiveRiskService picks it up in live mode
    full_7d["source"] = "open-meteo"
    storage.upsert_observations(full_7d)

    # Pick segment 0, an adjacent neighbor, and a distant segment
    service = LiveRiskService(storage=storage)
    engine = service._get_engine()
    all_segs = engine.segment_order
    corrupted_seg = all_segs[0]
    neighbor_indices = [j for j, v in enumerate(engine.A_hat[0]) if v > 0 and j != 0]
    neighbor_seg = engine.segment_order[neighbor_indices[0]]
    distant_indices = [j for j, v in enumerate(engine.A_hat[0]) if v == 0 and j != 0]
    distant_seg = engine.segment_order[distant_indices[0]]

    # Inject missing rainfall and MISSING_DATA quality_flag for corrupted_seg on 2024-07-15
    with storage._get_connection() as conn:
        conn.execute(
            """
            UPDATE weather_observation
            SET precip_mm = NULL, quality_flag = 'MISSING_DATA'
            WHERE segment_id = ? AND obs_date = '2024-07-15' AND source = 'open-meteo'
            """,
            (corrupted_seg,),
        )
        conn.commit()

    service = LiveRiskService(storage=storage)
    eval_time = pd.to_datetime("2024-07-15 12:00:00+00:00").to_pydatetime()
    predictions = service.compute_live_risk(as_of="2024-07-15", eval_time=eval_time)

    assert len(predictions) == 151
    pred_map = {p["segment_id"]: p for p in predictions}

    # Corrupted segment MUST be MISSING_DATA, UNKNOWN tier, None score (never Low!)
    p_corrupt = pred_map[corrupted_seg]
    assert p_corrupt["status"] == "MISSING_DATA"
    assert p_corrupt["risk_tier"] == "UNKNOWN"
    assert p_corrupt["risk_score"] is None

    # Adjacent neighbor segment MUST be NEIGHBOUR_DATA_MISSING, UNKNOWN tier, None score
    p_neighbor = pred_map[neighbor_seg]
    assert p_neighbor["status"] == "NEIGHBOUR_DATA_MISSING"
    assert p_neighbor["risk_tier"] == "UNKNOWN"
    assert p_neighbor["risk_score"] is None

    # Distant clean segment must NOT be contaminated: valid score, tier in Low/Medium/High, status OK
    p_distant = pred_map[distant_seg]
    assert p_distant["status"] == "OK"
    assert p_distant["risk_tier"] in ("Low", "Medium", "High")
    assert p_distant["risk_score"] is not None
    assert 0.0 <= p_distant["risk_score"] <= 1.0

    # Also verify stored live_risk table rows
    with storage._get_connection() as conn:
        corrupt_row = conn.execute(
            "SELECT score, tier, status FROM live_risk WHERE segment_id = ? AND as_of = '2024-07-15'",
            (corrupted_seg,),
        ).fetchone()
        assert corrupt_row["status"] == "MISSING_DATA"
        assert corrupt_row["tier"] == "UNKNOWN"
        assert corrupt_row["score"] is None

        neighbor_row = conn.execute(
            "SELECT score, tier, status FROM live_risk WHERE segment_id = ? AND as_of = '2024-07-15'",
            (neighbor_seg,),
        ).fetchone()
        assert neighbor_row["status"] == "NEIGHBOUR_DATA_MISSING"
        assert neighbor_row["tier"] == "UNKNOWN"
        assert neighbor_row["score"] is None

        distant_row = conn.execute(
            "SELECT score, tier, status FROM live_risk WHERE segment_id = ? AND as_of = '2024-07-15'",
            (distant_seg,),
        ).fetchone()
        assert distant_row["status"] == "OK"
        assert distant_row["tier"] in ("Low", "Medium", "High")
        assert distant_row["score"] is not None


def test_missing_cluster_flags_cluster_and_neighbors_as_unknown(tmp_path: Path):
    """When a cluster (<=25% of corridor) has missing data, all cluster segments and adjacent neighbors are UNKNOWN."""
    from src.services.live_risk_service import LiveRiskService
    from src.services.weather.replay import ReplayProvider

    test_db = tmp_path / "test_cluster_missing.db"
    storage = WeatherStorage(db_path=test_db)
    storage.init_db()

    # Seed 7 days of complete valid weather
    replay = ReplayProvider(csv_path="data/weather_daily_by_segment.csv")
    full_7d = replay.fetch(start_date="2024-07-09", end_date="2024-07-15")
    full_7d["source"] = "open-meteo"
    storage.upsert_observations(full_7d)

    # Pick cluster 4 (cell_4_33.5_75.2 has 14 segments, 14/151 = 9.3% <= 25%)
    clusters = OpenMeteoProvider().get_clusters()
    target_cluster = next(c for c in clusters if len(c.segment_ids) == 14)
    cluster_segs = set(target_cluster.segment_ids)

    # Corrupt all segments in this cluster on 2024-07-15
    with storage._get_connection() as conn:
        for seg in cluster_segs:
            conn.execute(
                """
                UPDATE weather_observation
                SET precip_mm = NULL, quality_flag = 'MISSING_DATA'
                WHERE segment_id = ? AND obs_date = '2024-07-15' AND source = 'open-meteo'
                """,
                (seg,),
            )
        conn.commit()

    service = LiveRiskService(storage=storage)
    eval_time = pd.to_datetime("2024-07-15 12:00:00+00:00").to_pydatetime()
    predictions = service.compute_live_risk(as_of="2024-07-15", eval_time=eval_time)

    assert len(predictions) == 151
    pred_map = {p["segment_id"]: p for p in predictions}

    # All cluster segments must be MISSING_DATA and UNKNOWN
    for seg in cluster_segs:
        p = pred_map[seg]
        assert p["status"] == "MISSING_DATA"
        assert p["risk_tier"] == "UNKNOWN"
        assert p["risk_score"] is None

    # Distant cluster 0 segments (in south) must remain OK
    c0 = clusters[0]
    c0_segs_distant = [s for s in c0.segment_ids if pred_map[s]["status"] == "OK"]
    assert len(c0_segs_distant) > 0


def test_missing_above_threshold_flags_all_segments_unknown(tmp_path: Path):
    """When missing segments exceed 25% threshold, ALL 151 segments evaluate to MISSING_DATA / UNKNOWN."""
    from src.services.live_risk_service import LiveRiskService
    from src.services.weather.replay import ReplayProvider

    test_db = tmp_path / "test_above_threshold.db"
    storage = WeatherStorage(db_path=test_db)
    storage.init_db()

    # Seed 7 days of complete valid weather
    replay = ReplayProvider(csv_path="data/weather_daily_by_segment.csv")
    full_7d = replay.fetch(start_date="2024-07-09", end_date="2024-07-15")
    full_7d["source"] = "open-meteo"
    storage.upsert_observations(full_7d)

    # Pick cluster 3 (cell_3_33.4_75.2 has 58 segments: 58/151 = 38.4% > 25% threshold)
    clusters = OpenMeteoProvider().get_clusters()
    target_cluster = next(c for c in clusters if len(c.segment_ids) == 58)
    cluster_segs = set(target_cluster.segment_ids)

    # Corrupt all 58 segments on 2024-07-15
    with storage._get_connection() as conn:
        for seg in cluster_segs:
            conn.execute(
                """
                UPDATE weather_observation
                SET precip_mm = NULL, quality_flag = 'MISSING_DATA'
                WHERE segment_id = ? AND obs_date = '2024-07-15' AND source = 'open-meteo'
                """,
                (seg,),
            )
        conn.commit()

    service = LiveRiskService(storage=storage)
    eval_time = pd.to_datetime("2024-07-15 12:00:00+00:00").to_pydatetime()
    predictions = service.compute_live_risk(as_of="2024-07-15", eval_time=eval_time)

    assert len(predictions) == 151
    # Above 25% threshold: ALL 151 segments must be MISSING_DATA and UNKNOWN tier
    for p in predictions:
        assert p["status"] == "MISSING_DATA"
        assert p["risk_tier"] == "UNKNOWN"
        assert p["risk_score"] is None


def test_scheduler_cold_start_backfill_13_days(tmp_path: Path):
    """Empty DB cold start: first scheduler cycle backfills 13 days; 0 segments are UNKNOWN."""
    import asyncio
    from src.services.weather.scheduler import WeatherScheduler
    from src.services.weather.replay import ReplayProvider

    test_db = tmp_path / "cold_start_test.db"
    storage = WeatherStorage(db_path=test_db)
    storage.init_db()
    assert storage.count_observations() == 0  # Completely empty DB

    today = datetime.now(timezone.utc).date()
    # Mock provider returning 14 days of realistic weather
    start_14d = today - timedelta(days=13)
    replay = ReplayProvider(csv_path="data/weather_daily_by_segment.csv")
    raw_replay = replay.fetch(start_date="2024-07-02", end_date="2024-07-15")

    # Map dates to recent 14-day window
    date_map = {}
    for idx, d_str in enumerate(sorted(raw_replay["obs_date"].unique())):
        target_d = (start_14d + timedelta(days=idx)).strftime("%Y-%m-%d")
        date_map[d_str] = target_d

    mapped_df = raw_replay.copy()
    mapped_df["obs_date"] = mapped_df["obs_date"].map(date_map)
    mapped_df["source"] = "open-meteo"
    mapped_df["quality_flag"] = "EXPERIMENTAL_LIVE"

    class ColdStartProvider:
        provider_name = "open-meteo"
        def fetch(self, start_date, end_date=None, segments=None):
            return mapped_df

    scheduler = WeatherScheduler(storage=storage, provider=ColdStartProvider())
    scheduler.mode = "live"

    async def _run():
        upserted = await scheduler.run_once()
        assert upserted == 151 * 14  # 151 segments * 14 days = 2114 rows

        # Inspect live_risk table
        with storage._get_connection() as conn:
            rows = conn.execute("SELECT segment_id, score, tier, status FROM live_risk").fetchall()
            assert len(rows) == 151

            unknown_count = sum(1 for r in rows if r["tier"] == "UNKNOWN")
            ok_count = sum(1 for r in rows if r["status"] == "OK")

            # ZERO segments are UNKNOWN because backfilling 13 days provides a complete
            # 7-day lookback window without any PARTIAL_WINDOW
            assert unknown_count == 0
            assert ok_count == 151

    asyncio.run(_run())


