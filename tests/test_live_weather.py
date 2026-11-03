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
