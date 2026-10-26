"""Global pytest fixtures and test configuration for RouteWise."""
from __future__ import annotations

import os
import sys
import tempfile
import sqlite3
import shutil
from pathlib import Path

# 1. Guarantee repo root on sys.path
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# 2. Ensure test secret key and environment configuration BEFORE importing settings
os.environ["ROUTEWISE_SECRET_KEY"] = "pytest-test-secret-key-32-characters-long-safe-for-local-testing"
os.environ["ROUTEWISE_DEMO_MODE"] = "true"
os.environ["DEMO_PATROL_PASSWORD"] = "TestPatrolPass123!"
os.environ["DEMO_USER_PASSWORD"] = "TestUserPass123!"

# Create session temporary directories for DB and uploads
_TEST_TEMP_DIR = Path(tempfile.mkdtemp(prefix="routewise_test_"))
_TEST_DB_PATH = _TEST_TEMP_DIR / "routewise_test.db"
_TEST_UPLOADS_DIR = _TEST_TEMP_DIR / "uploads"
_TEST_UPLOADS_DIR.mkdir(parents=True, exist_ok=True)

os.environ["ROUTEWISE_DB_PATH"] = str(_TEST_DB_PATH)
os.environ["ROUTEWISE_UPLOADS_DIR"] = str(_TEST_UPLOADS_DIR)

import pytest
from src.api.config import settings
from src.services.auth_service import auth_service
from src.services.report_service import report_service
from src.services.corridor_service import corridor_service


def _init_test_database(db_path: Path) -> None:
    """Creates tables and seeds test accounts and weather slice in isolated test DB."""
    # Override service paths to point to test database and uploads directory
    object.__setattr__(settings, "db_path", db_path)
    object.__setattr__(settings, "uploads_dir", _TEST_UPLOADS_DIR)
    auth_service.db_path = db_path
    report_service.db_path = db_path
    report_service.uploads_dir = _TEST_UPLOADS_DIR / "reports"
    corridor_service.db_path = db_path

    # Initialize users and reports schema
    auth_service._init_db()
    report_service._init_db()

    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        # Create segment_weather table with indexes
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS segment_weather (
                segment_id TEXT,
                date TEXT,
                precip_mm REAL,
                snowfall_mm_we REAL,
                temp_mean_c REAL,
                temp_min_c REAL,
                snow_depth_m REAL,
                precip_3d_mm REAL,
                precip_7d_mm REAL
            );
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_sw_date_seg ON segment_weather(date, segment_id);")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_sw_seg_date ON segment_weather(segment_id, date);")

        # Seed test users
        now = "2026-10-01T00:00:00Z"

        # 1. Demo commuter user
        user_salt = auth_service._hash_password("TestUserPass123!", "salt")[:32]
        user_hash = auth_service._hash_password("TestUserPass123!", user_salt)
        conn.execute(
            """
            INSERT OR REPLACE INTO users (id, email, name, password_hash, salt, role, preferred_vehicle, created_at, is_simulated)
            VALUES (1, 'demo@routewise.ai', 'Dr. Kabir Sharma', ?, ?, 'user', 'Car', ?, 1)
            """,
            (user_hash, user_salt, now),
        )

        # 2. Demo patrol officer
        patrol_salt = auth_service._hash_password("TestPatrolPass123!", "salt")[:32]
        patrol_hash = auth_service._hash_password("TestPatrolPass123!", patrol_salt)
        conn.execute(
            """
            INSERT OR REPLACE INTO users (id, email, name, password_hash, salt, role, preferred_vehicle, created_at, is_simulated)
            VALUES (2, 'patrol@routewise.ai', 'Inspector Amit Rathore', ?, ?, 'patrol', 'Patrol Vehicle', ?, 1)
            """,
            (patrol_hash, patrol_salt, now),
        )

        # 3. Demo logistics user
        conn.execute(
            """
            INSERT OR REPLACE INTO users (id, email, name, password_hash, salt, role, preferred_vehicle, created_at, is_simulated)
            VALUES (3, 'logistics@routewise.ai', 'Tariq Ahmad', ?, ?, 'user', 'Truck', ?, 1)
            """,
            (user_hash, user_salt, now),
        )

        # 4. Seed a small weather slice from CSV (first 500 rows if present)
        csv_path = REPO_ROOT / "data" / "weather_daily_by_segment.csv"
        if csv_path.exists():
            import csv
            with open(csv_path, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                rows = []
                for i, r in enumerate(reader):
                    if i >= 1000:
                        break
                    rows.append((
                        r.get("segment_id"),
                        r.get("date"),
                        float(r["precip_mm"]) if r.get("precip_mm") else 0.0,
                        float(r["snowfall_mm_we"]) if r.get("snowfall_mm_we") else 0.0,
                        float(r["temp_mean_c"]) if r.get("temp_mean_c") else 0.0,
                        float(r["temp_min_c"]) if r.get("temp_min_c") else 0.0,
                        float(r["snow_depth_m"]) if r.get("snow_depth_m") else 0.0,
                        float(r["precip_3d_mm"]) if r.get("precip_3d_mm") else 0.0,
                        float(r["precip_7d_mm"]) if r.get("precip_7d_mm") else 0.0,
                    ))
                if rows:
                    conn.executemany(
                        """
                        INSERT INTO segment_weather (
                            segment_id, date, precip_mm, snowfall_mm_we, temp_mean_c, temp_min_c, snow_depth_m, precip_3d_mm, precip_7d_mm
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        rows,
                    )
        conn.commit()


_init_test_database(_TEST_DB_PATH)


@pytest.fixture(scope="session", autouse=True)
def isolated_test_environment():
    """Ensures every test runs against isolated temporary DB and upload directories."""
    yield
    # Cleanup session temp directory
    try:
        shutil.rmtree(_TEST_TEMP_DIR, ignore_errors=True)
    except Exception:
        pass
