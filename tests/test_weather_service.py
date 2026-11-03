"""Unit and Integration Tests for RouteWise Weather Services and Replay Provider (Step 1).

Verifies:
1. Checkpoint metadata dynamic columns and CSV header feature names match exact expected order.
2. ReplayProvider fetches valid daily observations from CSV with source="replay".
3. WeatherStorage creates weather_observation table in runtime DB with unique constraint on (segment_id, obs_date, source).
4. Replay ingestion fills the table idempotently: re-running creates zero duplicates.
5. Rolling precipitation calculation matches week2b_process_weather.py specification.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path
import pandas as pd
import pytest

from src.services.weather.base import (
    EXPECTED_DYNAMIC_FEATURES,
    load_checkpoint_dynamic_columns,
    load_csv_dynamic_columns,
)
from src.services.weather.replay import ReplayProvider
from src.services.weather.rolling import compute_rolling_precipitation
from src.services.weather.storage import WeatherStorage


def test_feature_names_and_order_match_checkpoint_and_csv():
    """Verify that the 7 dynamic features match exactly between checkpoint and CSV."""
    checkpoint_cols = load_checkpoint_dynamic_columns("stgnn_best.pt")
    csv_cols = load_csv_dynamic_columns("data/weather_daily_by_segment.csv")

    assert checkpoint_cols == EXPECTED_DYNAMIC_FEATURES, (
        f"Checkpoint dynamic columns {checkpoint_cols} do not match expected {EXPECTED_DYNAMIC_FEATURES}"
    )
    assert csv_cols == EXPECTED_DYNAMIC_FEATURES, (
        f"CSV dynamic columns {csv_cols} do not match expected {EXPECTED_DYNAMIC_FEATURES}"
    )
    assert checkpoint_cols == csv_cols


def test_replay_provider_fetches_valid_dataframe():
    """Verify ReplayProvider loads requested date range with source='replay'."""
    provider = ReplayProvider(csv_path="data/weather_daily_by_segment.csv")
    assert provider.provider_name == "replay"

    # Test single-day fetch
    df_day = provider.fetch(start_date="2024-07-15", end_date="2024-07-15")
    assert not df_day.empty
    assert len(df_day) == 151  # 151 segments in corridor
    assert (df_day["source"] == "replay").all()
    assert (df_day["obs_date"] == "2024-07-15").all()

    # Verify column presence and ordering
    for feat in EXPECTED_DYNAMIC_FEATURES:
        assert feat in df_day.columns

    # Test segment filtering
    first_seg = df_day["segment_id"].iloc[0]
    df_single_seg = provider.fetch(start_date="2024-07-15", end_date="2024-07-16", segments=[first_seg])
    assert len(df_single_seg) == 2  # 2 dates for 1 segment
    assert (df_single_seg["segment_id"] == first_seg).all()


def test_weather_storage_idempotence_and_no_duplicates(tmp_path: Path):
    """Verify WeatherStorage table creation and idempotent upserts with zero duplicates."""
    test_db = tmp_path / "test_live_weather.db"
    storage = WeatherStorage(db_path=test_db)
    storage.init_db()

    # Check table and index creation in SQLite
    with sqlite3.connect(test_db) as conn:
        tables = [
            r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        ]
        assert "weather_observation" in tables

        indices = [
            r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='index'").fetchall()
        ]
        assert "idx_weather_obs_date" in indices
        assert "idx_weather_obs_seg_date" in indices

    # Fetch 2 days of replay observations
    provider = ReplayProvider(csv_path="data/weather_daily_by_segment.csv")
    df_batch = provider.fetch(start_date="2024-07-10", end_date="2024-07-11")
    assert len(df_batch) == 302  # 151 segments * 2 days

    # 1. First ingestion
    inserted_first = storage.upsert_observations(df_batch)
    assert inserted_first == 302
    assert storage.count_observations() == 302

    # 2. Second ingestion with identical data (idempotence verification)
    inserted_second = storage.upsert_observations(df_batch)
    assert inserted_second == 302
    # Crucial assertion: Total count MUST remain 302, zero duplicate rows inserted!
    assert storage.count_observations() == 302

    # 3. Verify querying capabilities
    obs_queried = storage.get_observations(start_date="2024-07-10", end_date="2024-07-10")
    assert len(obs_queried) == 151
    assert (obs_queried["obs_date"] == "2024-07-10").all()
    assert (obs_queried["source"] == "replay").all()

    # 4. Verify latest date and timestamps
    assert storage.get_latest_observation_date() == "2024-07-11"
    assert storage.get_latest_fetched_at() is not None


def test_compute_rolling_precipitation():
    """Verify rolling 3-day and 7-day precipitation sums match week2b_process_weather.py."""
    data = {
        "segment_id": ["seg_A"] * 8,
        "obs_date": [f"2024-07-0{i}" for i in range(1, 9)],
        "precip_mm": [10.0, 20.0, 30.0, 0.0, 0.0, 5.0, 10.0, 15.0],
    }
    df = pd.DataFrame(data)
    res = compute_rolling_precipitation(df)

    # 3-day rolling sum:
    # Day 1: 10
    # Day 2: 10 + 20 = 30
    # Day 3: 10 + 20 + 30 = 60
    # Day 4: 20 + 30 + 0 = 50
    # Day 5: 30 + 0 + 0 = 30
    # Day 6: 0 + 0 + 5 = 5
    # Day 7: 0 + 5 + 10 = 15
    # Day 8: 5 + 10 + 15 = 30
    expected_3d = [10.0, 30.0, 60.0, 50.0, 30.0, 5.0, 15.0, 30.0]
    assert list(res["precip_3d_mm"]) == expected_3d

    # 7-day rolling sum:
    # Day 1..7 sum = 10+20+30+0+0+5+10 = 75
    # Day 2..8 sum = 20+30+0+0+5+10+15 = 80
    assert res["precip_7d_mm"].iloc[6] == 75.0
    assert res["precip_7d_mm"].iloc[7] == 80.0
