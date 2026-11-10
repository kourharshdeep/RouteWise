"""Tests for Weather Scheduler and Open-Meteo per-cluster bounded retry resilience (Task 3b Phase E/F).

Invariants verified:
1. Per-cluster bounded retry (N=3, exponential backoff, timeout 5s).
2. Failure in one cluster is non-blocking to other corridor clusters.
3. Failed clusters leave segments absent (no last-known substitution).
4. Missing telemetry propagates to LiveRiskService as MISSING_DATA / UNKNOWN (never Low, never 0.0).
5. Guardrail invariants (>25% missing triggers corridor-level UNKNOWN) remain intact.
"""
from __future__ import annotations

import logging
import urllib.error
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Optional
import pandas as pd
import pytest

from src.services.weather.base import EXPECTED_DYNAMIC_FEATURES
from src.services.weather.clustering import GridCluster, build_corridor_grid_clusters
from src.services.weather.open_meteo import OpenMeteoProvider
from src.services.weather.scheduler import WeatherScheduler
from src.services.weather.storage import WeatherStorage
from src.services.live_risk_service import LiveRiskService


def _mock_day_response(dates: List[str]) -> dict:
    return {
        "daily": {
            "time": dates,
            "precipitation_sum": [5.0] * len(dates),
            "snowfall_sum": [0.0] * len(dates),
            "temperature_2m_mean": [12.0] * len(dates),
            "temperature_2m_min": [7.0] * len(dates),
        },
        "hourly": {
            "time": [f"{d}T{h:02d}:00Z" for d in dates for h in range(24)],
            "snow_depth": [0.0] * (len(dates) * 24),
        },
    }


def test_cluster_transient_failure_then_success():
    """Cluster fetch retries on transient network error with bounded backoff and succeeds."""
    mock_data = _mock_day_response(["2026-11-01"])
    call_count = 0
    delays_recorded: List[float] = []

    def transient_fetcher(url: str, timeout: float) -> dict:
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise urllib.error.URLError("Connection reset by peer")
        return mock_data

    provider = OpenMeteoProvider(
        fetcher=transient_fetcher,
        max_retries=3,
        backoff_factor=0.5,
        sleep_fn=delays_recorded.append,
    )

    cluster = provider.get_clusters()[0]
    result = provider.fetch_cluster_raw(
        lat=cluster.latitude,
        lon=cluster.longitude,
        start_date="2026-11-01",
        end_date="2026-11-01",
    )

    assert result is not None
    assert call_count == 2
    # Verify delay calculation: attempt 1 backoff is 0.5 * (2**1) = 1.0s
    assert len(delays_recorded) == 1
    assert delays_recorded[0] == pytest.approx(1.0)


def test_cluster_permanent_failure_isolated_non_blocking(caplog):
    """Failure in one cluster does not block other clusters and does not substitute last-known."""
    clusters = build_corridor_grid_clusters()
    assert len(clusters) >= 2, "Corridor requires at least 2 clusters for isolation test"
    failed_cluster = clusters[0]
    succeeded_cluster = clusters[1]

    delays_recorded: List[float] = []

    def partial_failure_fetcher(url: str, timeout: float) -> dict:
        # If URL matches coordinates of failed_cluster, fail permanently
        coord_match = f"latitude={failed_cluster.latitude}&longitude={failed_cluster.longitude}"
        if coord_match in url:
            raise urllib.error.URLError("Permanent cluster connection refusal")
        return _mock_day_response(["2026-11-01"])

    provider = OpenMeteoProvider(
        fetcher=partial_failure_fetcher,
        max_retries=3,
        backoff_factor=0.5,
        sleep_fn=delays_recorded.append,
    )

    with caplog.at_level(logging.WARNING):
        df = provider.fetch(
            start_date="2026-11-01",
            end_date="2026-11-01",
            segments=failed_cluster.segment_ids + succeeded_cluster.segment_ids,
        )

    # 1. Output must not be completely empty: successful cluster segments are present
    assert not df.empty
    returned_segments = set(df["segment_id"].unique())

    # 2. Succeeded cluster segments must all be present
    for sid in succeeded_cluster.segment_ids:
        assert sid in returned_segments

    # 3. Failed cluster segments must be absent (no synthetic or last-known substitution)
    for sid in failed_cluster.segment_ids:
        assert sid not in returned_segments

    # 4. Warning logged with cluster ID
    warning_logged = any(failed_cluster.cluster_id in record.message for record in caplog.records)
    assert warning_logged, f"Expected warning mentioning {failed_cluster.cluster_id}"


def test_retry_count_is_bounded():
    """Verify that cluster retry terminates strictly at max_retries attempts."""
    call_count = 0
    delays_recorded: List[float] = []

    def failing_fetcher(url: str, timeout: float) -> dict:
        nonlocal call_count
        call_count += 1
        raise OSError("Host unreachable")

    provider = OpenMeteoProvider(
        fetcher=failing_fetcher,
        max_retries=3,
        backoff_factor=0.5,
        sleep_fn=delays_recorded.append,
    )

    res = provider.fetch_cluster_raw(33.25, 75.20, "2026-11-01", "2026-11-01")
    assert res is None
    # Strictly 3 attempts (no runaway loop)
    assert call_count == 3
    # Two sleeps between 3 attempts: attempt 1 -> 1.0s, attempt 2 -> 2.0s
    assert len(delays_recorded) == 2
    assert delays_recorded[0] == pytest.approx(1.0)
    assert delays_recorded[1] == pytest.approx(2.0)


def test_scheduler_passes_resilience_parameters_to_provider(tmp_path):
    """WeatherScheduler configures OpenMeteoProvider with cluster retry bounds and timeout."""
    storage = WeatherStorage(db_path=str(tmp_path / "test_resilience.db"))
    scheduler = WeatherScheduler(
        storage=storage,
        max_cluster_retries=3,
        cluster_timeout_seconds=10.0,
    )
    scheduler.mode = "live"
    provider = scheduler._get_provider()
    assert isinstance(provider, OpenMeteoProvider)
    assert provider.max_retries == 3
    assert provider.timeout_seconds == 10.0


def test_missing_cluster_segments_evaluate_unknown_in_risk_service(tmp_path):
    """When a cluster fails to ingest, LiveRiskService designates absent segments as UNKNOWN/MISSING_DATA."""
    storage = WeatherStorage(db_path=str(tmp_path / "risk_resilience.db"))
    risk_service = LiveRiskService(storage=storage)

    # Ingest weather observations for only 10 segments (141 segments missing > 25% threshold)
    dates = [(date(2026, 11, 1) + timedelta(days=i)).isoformat() for i in range(7)]
    rows = []
    for d in dates:
        for seg_idx in range(10):
            rows.append({
                "segment_id": f"seg_{seg_idx:03d}",
                "obs_date": d,
                "precip_mm": 5.0,
                "snowfall_mm_we": 0.0,
                "temp_mean_c": 12.0,
                "temp_min_c": 7.0,
                "snow_depth_m": 0.0,
                "precip_3d_mm": 15.0,
                "precip_7d_mm": 35.0,
                "source": "open-meteo",
                "fetched_at": "2026-11-08T10:00:00Z",
                "quality_flag": "EXPERIMENTAL_LIVE",
            })
    storage.upsert_observations(pd.DataFrame(rows))

    # Evaluate live risk
    predictions = risk_service.compute_live_risk(as_of="2026-11-07", source="open-meteo")

    # Invariant: $>25% missing segments must cause entire corridor to evaluate as UNKNOWN / MISSING_DATA
    assert len(predictions) == 151
    assert all(p["risk_tier"] == "UNKNOWN" for p in predictions)
    assert all(p["status"] == "MISSING_DATA" for p in predictions)
    assert all(p["risk_score"] is None for p in predictions)

    latest = risk_service.get_latest_live_risk(as_of="2026-11-07")
    assert latest["summary"]["UNKNOWN"] == 151
    assert all(s["risk_tier"] == "UNKNOWN" for s in latest["segments"])
    assert all(s["status"] == "MISSING_DATA" for s in latest["segments"])
