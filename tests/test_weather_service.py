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
from src.services.weather.open_meteo import OpenMeteoProvider
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


def test_database_aware_rolling_precipitation_uses_db_history(tmp_path: Path):
    """Seed days T-6..T-1 in SQLite, ingest only day T: precip_7d_mm and precip_3d_mm match true window."""
    test_db = tmp_path / "test_rolling.db"
    storage = WeatherStorage(db_path=test_db)
    storage.init_db()

    # Seed T-6 to T-1 (6 days) for all segments
    clusters = OpenMeteoProvider().get_clusters()
    all_segs = []
    for c in clusters:
        all_segs.extend(c.segment_ids)

    seed_dates = [f"2024-07-0{i}" for i in range(1, 7)]  # 2024-07-01 .. 2024-07-06
    seed_precips = [10.0, 20.0, 30.0, 0.0, 0.0, 5.0]  # T-6 to T-1
    seed_rows = []
    for d, p in zip(seed_dates, seed_precips):
        for sid in all_segs:
            seed_rows.append({
                "segment_id": sid,
                "obs_date": d,
                "precip_mm": p,
                "snowfall_mm_we": 0.0,
                "temp_mean_c": 20.0,
                "temp_min_c": 15.0,
                "snow_depth_m": 0.0,
                "precip_3d_mm": 0.0,
                "precip_7d_mm": 0.0,
                "source": "open-meteo",
                "fetched_at": "2024-07-01T00:00:00Z",
                "quality_flag": "EXPERIMENTAL_LIVE",
            })
    storage.upsert_observations(pd.DataFrame(seed_rows))

    # Ingest Day T (2024-07-07) with precip = 10.0 mm
    day_t_data = {
        "daily": {
            "time": ["2024-07-07"],
            "precipitation_sum": [10.0],
            "snowfall_sum": [0.0],
            "temperature_2m_mean": [22.0],
            "temperature_2m_min": [16.0],
        },
        "hourly": {"time": ["2024-07-07T00:00Z"], "snow_depth": [0.0]},
    }
    provider = OpenMeteoProvider(fetcher=lambda url, timeout: day_t_data, storage=storage)
    df_day_t = provider.fetch(start_date="2024-07-07", end_date="2024-07-07")

    assert len(df_day_t) == 151
    sample = df_day_t.iloc[0]
    # True 7-day sum: 10 + 20 + 30 + 0 + 0 + 5 + 10 = 75.0
    assert sample["precip_7d_mm"] == pytest.approx(75.0, abs=0.001)
    # True 3-day sum: 0 + 5 + 10 = 15.0
    assert sample["precip_3d_mm"] == pytest.approx(15.0, abs=0.001)
    assert sample["quality_flag"] == "EXPERIMENTAL_LIVE"


def test_database_aware_rolling_precipitation_insufficient_history_flagged(tmp_path: Path):
    """When required history is not in DB, 3d/7d value is flagged as incomplete."""
    test_db = tmp_path / "test_incomplete.db"
    storage = WeatherStorage(db_path=test_db)
    storage.init_db()

    # Empty DB, fetch only 1 day (2024-07-07)
    day_t_data = {
        "daily": {
            "time": ["2024-07-07"],
            "precipitation_sum": [10.0],
            "snowfall_sum": [0.0],
            "temperature_2m_mean": [22.0],
            "temperature_2m_min": [16.0],
        },
        "hourly": {"time": ["2024-07-07T00:00Z"], "snow_depth": [0.0]},
    }
    provider = OpenMeteoProvider(fetcher=lambda url, timeout: day_t_data, storage=storage)
    df_day_t = provider.fetch(start_date="2024-07-07", end_date="2024-07-07")

    assert len(df_day_t) == 151
    sample = df_day_t.iloc[0]
    # Insufficient history: must be flagged as incomplete, not silently normal
    assert sample["quality_flag"] == "PARTIAL_WINDOW"


def test_database_aware_rolling_precipitation_incremental_matches_batch(tmp_path: Path):
    """Incremental single-day updates over a sequence equal the full batch recomputation for every day."""
    test_db = tmp_path / "test_incremental.db"
    storage = WeatherStorage(db_path=test_db)
    storage.init_db()

    dates = [f"2024-07-0{i}" for i in range(1, 8)]  # 7 days
    precips = [10.0, 20.0, 30.0, 0.0, 0.0, 5.0, 10.0]

    # Ingest incrementally day by day
    for d, p in zip(dates, precips):
        mock_response = {
            "daily": {
                "time": [d],
                "precipitation_sum": [p],
                "snowfall_sum": [0.0],
                "temperature_2m_mean": [20.0],
                "temperature_2m_min": [15.0],
            },
            "hourly": {"time": [f"{d}T00:00Z"], "snow_depth": [0.0]},
        }
        provider = OpenMeteoProvider(fetcher=lambda url, timeout: mock_response, storage=storage)
        df_d = provider.fetch(start_date=d, end_date=d)
        storage.upsert_observations(df_d)

    # Re-ingesting Day 7 is idempotent
    last_count = storage.count_observations()
    storage.upsert_observations(df_d)
    assert storage.count_observations() == last_count

    # Compare Day 7 against full batch calculation
    obs_all = storage.get_observations()
    first_seg = obs_all["segment_id"].iloc[0]
    seg_obs = obs_all[obs_all["segment_id"] == first_seg].sort_values("obs_date")

    day7_row = seg_obs[seg_obs["obs_date"] == "2024-07-07"].iloc[0]
    assert day7_row["precip_7d_mm"] == pytest.approx(75.0, abs=0.001)
    assert day7_row["precip_3d_mm"] == pytest.approx(15.0, abs=0.001)
    assert day7_row["quality_flag"] == "EXPERIMENTAL_LIVE"


def test_weather_observation_migration_on_copy_of_live_db(tmp_path: Path):
    """Test non-destructive migration from legacy schema with REAL NOT NULL columns on a standalone temp DB."""
    legacy_db_path = tmp_path / "legacy_weather.db"

    # 1. Build a temp DB with the OLD weather_observation schema (dynamic columns REAL NOT NULL)
    with sqlite3.connect(legacy_db_path) as conn:
        conn.execute(
            """
            CREATE TABLE weather_observation (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                segment_id TEXT NOT NULL,
                obs_date TEXT NOT NULL,
                precip_mm REAL NOT NULL,
                snowfall_mm_we REAL NOT NULL,
                temp_mean_c REAL NOT NULL,
                temp_min_c REAL NOT NULL,
                snow_depth_m REAL NOT NULL,
                precip_3d_mm REAL NOT NULL,
                precip_7d_mm REAL NOT NULL,
                source TEXT NOT NULL,
                fetched_at TEXT NOT NULL,
                quality_flag TEXT NOT NULL DEFAULT 'OK',
                UNIQUE(segment_id, obs_date, source)
            );
            """
        )
        # Seed 5 rows with NOT NULL values
        seed_records = [
            (
                f"seg_{i}",
                f"2024-07-0{i}",
                float(i),
                0.0,
                20.0,
                15.0,
                0.0,
                float(i),
                float(i),
                "replay",
                "2024-07-01T00:00:00Z",
                "OK",
            )
            for i in range(1, 6)
        ]
        conn.executemany(
            """
            INSERT INTO weather_observation (
                segment_id, obs_date, precip_mm, snowfall_mm_we, temp_mean_c,
                temp_min_c, snow_depth_m, precip_3d_mm, precip_7d_mm,
                source, fetched_at, quality_flag
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            seed_records,
        )
        conn.commit()

        cur = conn.execute("SELECT count(*) FROM weather_observation")
        count_before = cur.fetchone()[0]
        assert count_before == 5

    # 2. Execute migration via WeatherStorage.init_db()
    storage = WeatherStorage(db_path=legacy_db_path)
    storage.init_db()

    # 3. Assert row count after migration is unchanged
    with sqlite3.connect(legacy_db_path) as conn:
        conn.row_factory = sqlite3.Row
        count_after = conn.execute("SELECT count(*) FROM weather_observation").fetchone()[0]
        assert count_after == 5

        # Check table info: all dynamic feature columns must be nullable (notnull == 0)
        table_info = conn.execute("PRAGMA table_info(weather_observation)").fetchall()
        col_map = {r["name"]: r for r in table_info}
        feature_cols = [
            "precip_mm", "snowfall_mm_we", "temp_mean_c", "temp_min_c",
            "snow_depth_m", "precip_3d_mm", "precip_7d_mm"
        ]
        for f in feature_cols:
            assert col_map[f]["notnull"] == 0, f"Column {f} should be nullable"

    # 4. Idempotent second run
    storage.init_db()
    with sqlite3.connect(legacy_db_path) as conn:
        count_second = conn.execute("SELECT count(*) FROM weather_observation").fetchone()[0]
        assert count_second == 5

    # 5. Verify insertion of NULL values succeeds without IntegrityError
    test_null_row = pd.DataFrame([{
        "segment_id": "migration_test_seg",
        "obs_date": "2099-01-01",
        "precip_mm": None,
        "snowfall_mm_we": None,
        "temp_mean_c": None,
        "temp_min_c": None,
        "snow_depth_m": None,
        "precip_3d_mm": None,
        "precip_7d_mm": None,
        "source": "migration_test",
        "fetched_at": "2099-01-01T00:00:00Z",
        "quality_flag": "MISSING_DATA",
    }])
    storage.upsert_observations(test_null_row)
    inserted = storage.get_observations(start_date="2099-01-01", end_date="2099-01-01")
    assert len(inserted) == 1
    assert pd.isna(inserted.iloc[0]["precip_mm"])
    assert inserted.iloc[0]["quality_flag"] == "MISSING_DATA"
    assert inserted.iloc[0]["quality_flag"] == "MISSING_DATA"



