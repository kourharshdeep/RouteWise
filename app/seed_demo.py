"""CLI tool for seeding and removing simulated demo operational data.

Usage:
    python -m app.seed_demo          # Seeds demo accounts and simulated reports (is_simulated=1)
    python -m app.seed_demo --clear  # Deletes all accounts and reports flagged is_simulated=1
"""
from __future__ import annotations

import argparse
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

# Ensure repo root is on sys.path
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.api.config import settings
from src.services.auth_service import auth_service
from src.services.report_service import report_service


def clear_simulated_data() -> None:
    """Removes all users, reports, and status history flagged as simulated."""
    with auth_service._get_connection() as conn:
        # Get simulated report IDs to remove their status history
        sim_report_rows = conn.execute("SELECT id FROM reports WHERE is_simulated = 1").fetchall()
        sim_report_ids = [r["id"] for r in sim_report_rows]

        for rid in sim_report_ids:
            conn.execute("DELETE FROM report_status_history WHERE report_id = ?", (rid,))

        reports_deleted = conn.execute("DELETE FROM reports WHERE is_simulated = 1").rowcount
        users_deleted = conn.execute("DELETE FROM users WHERE is_simulated = 1").rowcount
        conn.commit()

    print(f"Cleared simulated demo data successfully:")
    print(f"  - Deleted {reports_deleted} simulated field report(s)")
    print(f"  - Deleted {len(sim_report_ids)} associated status audit history record(s)")
    print(f"  - Deleted {users_deleted} simulated demo user account(s)")


def seed_simulated_data() -> None:
    """Seeds demo user, demo patrol officer, and 5 realistic simulated reports."""
    # 1. Clear any prior simulated data to avoid duplicates
    clear_simulated_data()

    # 2. Seed Demo Patrol Account
    patrol_email = "patrol@routewise.ai"
    patrol_name = "Inspector Amit Rathore (NH-44 Patrol)"
    patrol_pwd = settings.demo_patrol_password
    patrol_profile = auth_service.create_patrol_user(
        email=patrol_email,
        name=patrol_name,
        password=patrol_pwd,
        is_simulated=1,
    )

    # 3. Seed Demo Commuter Account
    user_email = "demo@routewise.ai"
    user_name = "Dr. Kabir Sharma"
    user_pwd = "routewise2026"
    with auth_service._get_connection() as conn:
        salt = auth_service._hash_password(user_pwd, "salt")[:32]
        pwd_hash = auth_service._hash_password(user_pwd, salt)
        now = datetime.now(timezone.utc).isoformat()
        existing_commuter = conn.execute("SELECT id FROM users WHERE email = ?", (user_email,)).fetchone()
        if existing_commuter:
            commuter_id = existing_commuter["id"]
            conn.execute(
                """
                UPDATE users
                SET name = ?, password_hash = ?, salt = ?, role = 'user', preferred_vehicle = 'Car', is_simulated = 1
                WHERE id = ?
                """,
                (user_name, pwd_hash, salt, commuter_id),
            )
        else:
            cursor = conn.execute(
                """
                INSERT INTO users (email, name, password_hash, salt, role, preferred_vehicle, created_at, is_simulated)
                VALUES (?, ?, ?, ?, 'user', 'Car', ?, 1)
                """,
                (user_email, user_name, pwd_hash, salt, now),
            )
            commuter_id = cursor.lastrowid
        logistics_email = "logistics@routewise.ai"
        logistics_name = "Tariq Ahmad (Kashmir Freight)"
        existing_log = conn.execute("SELECT id FROM users WHERE email = ?", (logistics_email,)).fetchone()
        if existing_log:
            conn.execute(
                """
                UPDATE users
                SET name = ?, password_hash = ?, salt = ?, role = 'user', preferred_vehicle = 'Truck', is_simulated = 1
                WHERE id = ?
                """,
                (logistics_name, pwd_hash, salt, existing_log["id"]),
            )
        else:
            conn.execute(
                """
                INSERT INTO users (email, name, password_hash, salt, role, preferred_vehicle, created_at, is_simulated)
                VALUES (?, ?, ?, ?, 'user', 'Truck', ?, 1)
                """,
                (logistics_email, logistics_name, pwd_hash, salt, now),
            )
        conn.commit()

    # 4. Seed 5 Realistic Corridor Incidents with is_simulated = 1
    # Positions mapped along the NH-44 Ramban-Banihal stretch
    demo_reports = [
        {
            "client_uuid": f"sim-demo-{uuid.uuid4().hex[:12]}",
            "category": "shooting_stones",
            "description": "Intermittent rockfall from cutting face near Cafeteria Morh. Caution advised.",
            "latitude": 33.2435,
            "longitude": 75.2415,
            "status": "submitted",
            "assigned_to": None,
            "history": [
                ("submitted", commuter_id, "user", "Incident reported by commuter via mobile capture"),
            ],
        },
        {
            "client_uuid": f"sim-demo-{uuid.uuid4().hex[:12]}",
            "category": "landslide",
            "description": "Debris and muck sliding across northbound lane near Seri. Single line crawl.",
            "latitude": 33.2710,
            "longitude": 75.2280,
            "status": "verified",
            "assigned_to": None,
            "history": [
                ("submitted", commuter_id, "user", "Field observation captured"),
                ("verified", patrol_profile.id, "patrol", "Confirmed via CCTV / checkpoint scout at Seri"),
            ],
        },
        {
            "client_uuid": f"sim-demo-{uuid.uuid4().hex[:12]}",
            "category": "single_lane_or_obstruction",
            "description": "Heavy goods truck broken down on blind curve near Digdol. Traffic marshaled.",
            "latitude": 33.3150,
            "longitude": 75.2010,
            "status": "assigned",
            "assigned_to": patrol_profile.id,
            "history": [
                ("submitted", commuter_id, "user", "Breakdown reported"),
                ("verified", patrol_profile.id, "patrol", "Obstruction verified with TCU Ramban"),
                ("assigned", patrol_profile.id, "patrol", f"Assigned to {patrol_name} for recovery convoy"),
            ],
        },
        {
            "client_uuid": f"sim-demo-{uuid.uuid4().hex[:12]}",
            "category": "road_damage",
            "description": "Eroded asphalt and edge subsidence at Ramsu culvert. Steel plating installed.",
            "latitude": 33.3750,
            "longitude": 75.1950,
            "status": "resolved",
            "assigned_to": patrol_profile.id,
            "history": [
                ("submitted", commuter_id, "user", "Edge damage reported"),
                ("verified", patrol_profile.id, "patrol", "Assessed by NHAI maintenance engineering"),
                ("assigned", patrol_profile.id, "patrol", "Assigned for immediate surface patch"),
                ("resolved", patrol_profile.id, "patrol", "Temporary cold mix and steel plate barrier installed. Traffic normal."),
            ],
        },
        {
            "client_uuid": f"sim-demo-{uuid.uuid4().hex[:12]}",
            "category": "flooding",
            "description": "Runoff pooling across carriageway at Banihal South tunnel approach.",
            "latitude": 33.4850,
            "longitude": 75.1980,
            "status": "submitted",
            "assigned_to": None,
            "history": [
                ("submitted", commuter_id, "user", "Standing water reported on slow lane"),
            ],
        },
    ]

    with auth_service._get_connection() as conn:
        for rep in demo_reports:
            report_id = str(uuid.uuid4())
            nearest_seg, dist_m = report_service.snap_to_corridor(rep["latitude"], rep["longitude"])
            now = datetime.now(timezone.utc).isoformat()

            conn.execute(
                """
                INSERT INTO reports (
                    id, client_uuid, reporter_id, category, description, latitude, longitude,
                    nearest_segment_id, nearest_segment_distance_m, photo_path, status, assigned_to,
                    client_created_at, created_at, updated_at, is_simulated
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, ?, ?, ?, ?, ?, 1)
                """,
                (
                    report_id,
                    rep["client_uuid"],
                    commuter_id,
                    rep["category"],
                    rep["description"],
                    rep["latitude"],
                    rep["longitude"],
                    nearest_seg,
                    dist_m,
                    rep["status"],
                    rep["assigned_to"],
                    now,
                    now,
                    now,
                ),
            )

            # Insert history entries
            last_status = None
            for step_status, actor_id, actor_role, note in rep["history"]:
                conn.execute(
                    """
                    INSERT INTO report_status_history (
                        report_id, from_status, to_status, actor_id, actor_role, note, timestamp
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (report_id, last_status, step_status, actor_id, actor_role, note, now),
                )
                last_status = step_status

        conn.commit()

    print("Demo operational data successfully seeded (is_simulated=1):")
    print(f"  - Patrol Officer: {patrol_email} (Password: {patrol_pwd})")
    print(f"  - Public Commuter: {user_email} (Password: {user_pwd})")
    print(f"  - 5 simulated field reports snapped along NH-44 Ramban-Banihal.")
    print("All simulated items are visibly badged 'Simulated demo data' in the UI.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed or clear RouteWise simulated demo data.")
    parser.add_argument(
        "--clear",
        action="store_true",
        help="Remove all demo users and simulated reports flagged is_simulated=1",
    )
    args = parser.parse_args()

    if args.clear:
        clear_simulated_data()
    else:
        seed_simulated_data()


if __name__ == "__main__":
    main()
