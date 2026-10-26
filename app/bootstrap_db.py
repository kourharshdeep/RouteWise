"""RouteWise Database Bootstrap Tool.

Idempotently creates all database tables required by RouteWise services
and populates the segment_weather table from data/weather_daily_by_segment.csv.

Usage:
    python -m app.bootstrap_db
    python -m app.bootstrap_db --db-path data/routewise_local.db
"""
from __future__ import annotations

import argparse
import csv
import logging
import sqlite3
import sys
import time
from pathlib import Path

# Ensure repository root is on sys.path
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.api.config import settings

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("bootstrap_db")


def bootstrap_database(
    db_path: Path | None = None,
    weather_csv_path: Path | None = None,
) -> None:
    """Initializes tables and indexes, and populates segment_weather idempotently."""
    target_db = Path(db_path or settings.db_path)
    csv_path = Path(weather_csv_path or settings.weather_daily_path)

    # 1. Ensure target directory exists
    target_db.parent.mkdir(parents=True, exist_ok=True)
    logger.info("Bootstrapping RouteWise database at: %s", target_db)

    conn = sqlite3.connect(target_db)
    conn.execute("PRAGMA journal_mode = WAL;")
    conn.execute("PRAGMA synchronous = NORMAL;")

    try:
        # 2. DDL: users table
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT UNIQUE NOT NULL COLLATE NOCASE,
                name TEXT NOT NULL,
                password_hash TEXT NOT NULL,
                salt TEXT NOT NULL,
                role TEXT NOT NULL DEFAULT 'user',
                preferred_vehicle TEXT NOT NULL DEFAULT 'Car',
                created_at TEXT NOT NULL,
                is_simulated INTEGER NOT NULL DEFAULT 0
            );
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_users_email ON users(email);")

        # 3. DDL: reports table
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS reports (
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
                is_simulated INTEGER NOT NULL DEFAULT 0,
                FOREIGN KEY(reporter_id) REFERENCES users(id),
                FOREIGN KEY(assigned_to) REFERENCES users(id)
            );
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_reports_client_uuid ON reports(client_uuid);")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_reports_reporter ON reports(reporter_id);")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_reports_status ON reports(status);")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_reports_segment ON reports(nearest_segment_id);")

        # 4. DDL: report_status_history table
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS report_status_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                report_id TEXT NOT NULL,
                from_status TEXT,
                to_status TEXT NOT NULL,
                actor_id INTEGER NOT NULL,
                actor_role TEXT NOT NULL,
                note TEXT,
                timestamp TEXT NOT NULL,
                FOREIGN KEY(report_id) REFERENCES reports(id) ON DELETE CASCADE
            );
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_report_history_report ON report_status_history(report_id);")

        # 5. DDL: segment_weather table and required indexes
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS segment_weather (
                segment_id TEXT NOT NULL,
                date TEXT NOT NULL,
                precip_mm REAL,
                snowfall_mm_we REAL,
                temp_mean_c REAL,
                temp_min_c REAL,
                snow_depth_m REAL,
                precip_3d_mm REAL,
                precip_7d_mm REAL,
                PRIMARY KEY (segment_id, date)
            );
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_weather_date_segment ON segment_weather(date, segment_id);")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_weather_segment_date ON segment_weather(segment_id, date);")
        conn.commit()

        # 6. Populate segment_weather from read-only CSV
        if not csv_path.exists():
            logger.warning("Weather daily CSV not found at %s. Table created but unpopulated.", csv_path)
            return

        initial_count = conn.execute("SELECT COUNT(*) FROM segment_weather").fetchone()[0]
        if initial_count >= 275877:
            logger.info("segment_weather table is already fully populated (%d rows). Skipping CSV reload.", initial_count)
            return

        logger.info("Current segment_weather rows: %d. Loading from %s...", initial_count, csv_path)

        t0 = time.time()
        batch_size = 25000
        batch = []
        total_inserted = 0

        with open(csv_path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                batch.append((
                    row.get("segment_id"),
                    row.get("date"),
                    float(row["precip_mm"]) if row.get("precip_mm") else 0.0,
                    float(row["snowfall_mm_we"]) if row.get("snowfall_mm_we") else 0.0,
                    float(row["temp_mean_c"]) if row.get("temp_mean_c") else 0.0,
                    float(row["temp_min_c"]) if row.get("temp_min_c") else 0.0,
                    float(row["snow_depth_m"]) if row.get("snow_depth_m") else 0.0,
                    float(row["precip_3d_mm"]) if row.get("precip_3d_mm") else 0.0,
                    float(row["precip_7d_mm"]) if row.get("precip_7d_mm") else 0.0,
                ))
                if len(batch) >= batch_size:
                    conn.executemany(
                        """
                        INSERT OR IGNORE INTO segment_weather (
                            segment_id, date, precip_mm, snowfall_mm_we, temp_mean_c, temp_min_c, snow_depth_m, precip_3d_mm, precip_7d_mm
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        batch,
                    )
                    conn.commit()
                    total_inserted += len(batch)
                    batch = []

            if batch:
                conn.executemany(
                    """
                    INSERT OR IGNORE INTO segment_weather (
                        segment_id, date, precip_mm, snowfall_mm_we, temp_mean_c, temp_min_c, snow_depth_m, precip_3d_mm, precip_7d_mm
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    batch,
                )
                conn.commit()
                total_inserted += len(batch)

        final_count = conn.execute("SELECT COUNT(*) FROM segment_weather").fetchone()[0]
        elapsed = time.time() - t0
        logger.info(
            "Bootstrap complete in %.2fs. Total segment_weather rows now: %d (added/verified %d rows).",
            elapsed,
            final_count,
            final_count - initial_count,
        )

    finally:
        conn.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Bootstrap RouteWise SQLite database and weather tables.")
    parser.add_argument("--db-path", type=Path, default=None, help="Custom SQLite database output path.")
    parser.add_argument("--weather-path", type=Path, default=None, help="Custom weather daily CSV input path.")
    args = parser.parse_args()

    bootstrap_database(db_path=args.db_path, weather_csv_path=args.weather_path)


if __name__ == "__main__":
    main()
