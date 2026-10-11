"""
Week 3: Create the offline SQLite database and prove it works
---------------------------------------------------------------
Run (venv active, from the RouteWise folder, with week3_offline_schema.sql beside it):
    python week3_create_db.py

What it does:
  1. Creates data/routewise_local.db from week3_offline_schema.sql
  2. Simulates an OFFLINE report: saves a hazard report + photo + queue entry
  3. Simulates coming back ONLINE: lists pending reports, marks one synced
  4. Prints the tables so you can screenshot them for your report
  5. Deletes the test rows, leaving an empty, ready database

Then open data/routewise_local.db with the SQLite Viewer extension and check
that the 4 tables exist: hazard_reports, photos, risk_cache, sync_queue.
"""
import os
import sqlite3
import uuid
from datetime import datetime, timezone

DB_PATH = "data/routewise_local.db"
SCHEMA = "week3_offline_schema.sql"


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def main():
    if not os.path.exists(SCHEMA):
        raise SystemExit(f"{SCHEMA} not found. Put it in the RouteWise folder.")
    os.makedirs("data", exist_ok=True)
    con = sqlite3.connect(DB_PATH)
    con.execute("PRAGMA foreign_keys = ON")
    with open(SCHEMA, encoding="utf-8") as f:
        con.executescript(f.read())

    tables = [r[0] for r in con.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")]
    print("Tables:", tables)
    expected = {"hazard_reports", "photos", "risk_cache", "sync_queue"}
    assert expected <= set(tables), f"Missing tables: {expected - set(tables)}"

    # --- 1. Phone is OFFLINE: user files a report (ids made on the device)
    rid, pid = str(uuid.uuid4()), str(uuid.uuid4())
    con.execute(
        "INSERT INTO hazard_reports (report_id, latitude, longitude, hazard_type, description, created_at) "
        "VALUES (?,?,?,?,?,?)",
        (rid, 33.2560, 75.2100, "landslide", "TEST: debris on road", now()))
    con.execute("INSERT INTO photos (photo_id, report_id, local_file_path) VALUES (?,?,?)",
                (pid, rid, "/storage/test/photo1.jpg"))
    con.execute("INSERT INTO sync_queue (report_id) VALUES (?)", (rid,))
    con.commit()
    print("\nSaved offline. Pending reports:",
          con.execute("SELECT report_id, sync_status FROM hazard_reports WHERE sync_status='pending'").fetchall())

    # --- 2. Phone is back ONLINE: sync service pushes it, then marks it done
    con.execute("UPDATE hazard_reports SET sync_status='synced', synced_at=? WHERE report_id=?", (now(), rid))
    con.execute("UPDATE photos SET uploaded=1 WHERE report_id=?", (rid,))
    con.execute("DELETE FROM sync_queue WHERE report_id=?", (rid,))
    con.commit()
    print("After sync:", con.execute("SELECT report_id, sync_status, synced_at FROM hazard_reports").fetchall())

    # --- 3. Foreign key check: a photo for a report that does not exist must fail
    try:
        con.execute("INSERT INTO photos (photo_id, report_id, local_file_path) VALUES (?,?,?)",
                    (str(uuid.uuid4()), "no-such-report", "x.jpg"))
        print("WARNING: foreign key not enforced")
    except sqlite3.IntegrityError:
        print("Foreign key check works (orphan photo rejected).")

    # --- 4. Clean the test rows
    for t in ("sync_queue", "photos", "hazard_reports"):
        con.execute(f"DELETE FROM {t}")
    con.commit()
    con.close()
    print(f"\nDone. Empty database ready at {DB_PATH}. Open it in SQLite Viewer.")


if __name__ == "__main__":
    main()