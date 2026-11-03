"""Runtime Weather Observation Storage.

Manages the runtime SQLite database table `weather_observation`:
- Schema: segment_id, obs_date, precip_mm, snowfall_mm_we, temp_mean_c, temp_min_c,
          snow_depth_m, precip_3d_mm, precip_7d_mm, source, fetched_at, quality_flag
- Unique constraint: (segment_id, obs_date, source)
- Indexes: obs_date, (segment_id, obs_date)
- Idempotent upsert logic to ensure duplicate calls do not insert duplicate rows.
"""
from __future__ import annotations

import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional, Sequence

import pandas as pd

from src.api.config import settings
from src.services.weather.base import EXPECTED_DYNAMIC_FEATURES

logger = logging.getLogger("weather_storage")


class WeatherStorage:
    """Manages weather observation persistence in the isolated runtime database."""

    def __init__(self, db_path: Path | str | None = None) -> None:
        self.db_path = Path(db_path or settings.live_db_path)

    def _get_connection(self) -> sqlite3.Connection:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode = WAL;")
        conn.execute("PRAGMA synchronous = NORMAL;")
        return conn

    def init_db(self) -> None:
        """Initializes weather_observation table and indexes idempotently."""
        with self._get_connection() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS weather_observation (
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
            conn.execute("CREATE INDEX IF NOT EXISTS idx_weather_obs_date ON weather_observation(obs_date);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_weather_obs_seg_date ON weather_observation(segment_id, obs_date);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_weather_obs_source ON weather_observation(source);")
            conn.commit()

    def upsert_observations(self, df: pd.DataFrame) -> int:
        """Idempotently upserts observations from a DataFrame into weather_observation.
        
        Returns:
            Count of rows processed.
        """
        if df.empty:
            return 0

        self.init_db()

        # Map date column name if provided as 'date' instead of 'obs_date'
        work_df = df.copy()
        if "obs_date" not in work_df.columns and "date" in work_df.columns:
            work_df["obs_date"] = work_df["date"]

        # Ensure required columns are present
        required = ["segment_id", "obs_date"] + EXPECTED_DYNAMIC_FEATURES
        for col in required:
            if col not in work_df.columns:
                raise ValueError(f"Missing required weather column: '{col}'")

        if "source" not in work_df.columns:
            work_df["source"] = "unknown"
        if "fetched_at" not in work_df.columns:
            work_df["fetched_at"] = datetime.now(timezone.utc).isoformat()
        if "quality_flag" not in work_df.columns:
            work_df["quality_flag"] = "OK"

        records = []
        for _, row in work_df.iterrows():
            records.append((
                str(row["segment_id"]),
                str(row["obs_date"]),
                float(row["precip_mm"]),
                float(row["snowfall_mm_we"]),
                float(row["temp_mean_c"]),
                float(row["temp_min_c"]),
                float(row["snow_depth_m"]),
                float(row["precip_3d_mm"]),
                float(row["precip_7d_mm"]),
                str(row["source"]),
                str(row["fetched_at"]),
                str(row["quality_flag"]),
            ))

        sql = """
            INSERT INTO weather_observation (
                segment_id, obs_date, precip_mm, snowfall_mm_we, temp_mean_c,
                temp_min_c, snow_depth_m, precip_3d_mm, precip_7d_mm,
                source, fetched_at, quality_flag
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(segment_id, obs_date, source) DO UPDATE SET
                precip_mm = excluded.precip_mm,
                snowfall_mm_we = excluded.snowfall_mm_we,
                temp_mean_c = excluded.temp_mean_c,
                temp_min_c = excluded.temp_min_c,
                snow_depth_m = excluded.snow_depth_m,
                precip_3d_mm = excluded.precip_3d_mm,
                precip_7d_mm = excluded.precip_7d_mm,
                fetched_at = excluded.fetched_at,
                quality_flag = excluded.quality_flag;
        """

        with self._get_connection() as conn:
            conn.executemany(sql, records)
            conn.commit()

        return len(records)

    def get_observations(
        self,
        start_date: str | None = None,
        end_date: str | None = None,
        segment_id: str | None = None,
        source: str | None = None,
    ) -> pd.DataFrame:
        """Retrieves observations matching filter criteria."""
        self.init_db()
        conditions = []
        params: List[str] = []

        if start_date:
            conditions.append("obs_date >= ?")
            params.append(start_date)
        if end_date:
            conditions.append("obs_date <= ?")
            params.append(end_date)
        if segment_id:
            conditions.append("segment_id = ?")
            params.append(segment_id)
        if source:
            conditions.append("source = ?")
            params.append(source)

        where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        query = f"""
            SELECT segment_id, obs_date, precip_mm, snowfall_mm_we, temp_mean_c,
                   temp_min_c, snow_depth_m, precip_3d_mm, precip_7d_mm,
                   source, fetched_at, quality_flag
            FROM weather_observation
            {where_clause}
            ORDER BY obs_date ASC, segment_id ASC;
        """

        with self._get_connection() as conn:
            rows = conn.execute(query, params).fetchall()

        if not rows:
            return pd.DataFrame(
                columns=["segment_id", "obs_date"] + EXPECTED_DYNAMIC_FEATURES + ["source", "fetched_at", "quality_flag"]
            )

        data = [dict(r) for r in rows]
        return pd.DataFrame(data)

    def count_observations(self, source: str | None = None) -> int:
        """Returns total number of observation rows."""
        self.init_db()
        with self._get_connection() as conn:
            if source:
                cur = conn.execute("SELECT COUNT(*) FROM weather_observation WHERE source = ?", (source,))
            else:
                cur = conn.execute("SELECT COUNT(*) FROM weather_observation")
            return cur.fetchone()[0]

    def get_latest_observation_date(self, source: str | None = None) -> Optional[str]:
        """Returns the most recent obs_date in the database."""
        self.init_db()
        with self._get_connection() as conn:
            if source:
                cur = conn.execute("SELECT MAX(obs_date) FROM weather_observation WHERE source = ?", (source,))
            else:
                cur = conn.execute("SELECT MAX(obs_date) FROM weather_observation")
            row = cur.fetchone()
            return row[0] if row and row[0] else None

    def get_latest_fetched_at(self, source: str | None = None) -> Optional[str]:
        """Returns the most recent fetched_at timestamp."""
        self.init_db()
        with self._get_connection() as conn:
            if source:
                cur = conn.execute("SELECT MAX(fetched_at) FROM weather_observation WHERE source = ?", (source,))
            else:
                cur = conn.execute("SELECT MAX(fetched_at) FROM weather_observation")
            row = cur.fetchone()
            return row[0] if row and row[0] else None


# Module-level default storage instance pointing to settings.live_db_path
weather_storage = WeatherStorage()

