-- Week 3: Offline-First Field Reporting Schema
-- ------------------------------------------------
-- Run with: sqlite3 routewise_local.db < week3_offline_schema.sql
-- This is the local DB that lives ON THE PHONE (Flutter uses this
-- via the `sqflite` package — same schema, no changes needed).

-- One row per hazard report a field user submits, online or offline.
CREATE TABLE IF NOT EXISTS hazard_reports (
    report_id       TEXT PRIMARY KEY,     -- client-generated UUID
                                           -- (generate on-device so
                                           -- offline reports still
                                           -- get a stable unique id)
    segment_id      TEXT,                 -- nearest graph edge id,
                                           -- resolved on-device if
                                           -- the corridor graph is
                                           -- cached locally (Week 1
                                           -- output, bundled with app)
    latitude        REAL NOT NULL,
    longitude        REAL NOT NULL,
    hazard_type     TEXT NOT NULL,        -- landslide/snow/flood/other
    description     TEXT,
    created_at      TEXT NOT NULL,        -- ISO 8601 timestamp, set
                                           -- on-device at capture time
    sync_status     TEXT NOT NULL DEFAULT 'pending'
                    CHECK (sync_status IN ('pending', 'synced', 'failed')),
    synced_at       TEXT                  -- NULL until synced
);

-- One row per photo attached to a report (a report can have several).
CREATE TABLE IF NOT EXISTS photos (
    photo_id        TEXT PRIMARY KEY,     -- client-generated UUID
    report_id       TEXT NOT NULL REFERENCES hazard_reports(report_id),
    local_file_path TEXT NOT NULL,        -- path on device storage
    uploaded        INTEGER NOT NULL DEFAULT 0  -- 0/1, mirrors
                                           -- the parent report's
                                           -- sync_status once synced
);

-- Cache of the last risk score fetched per segment, so the app can
-- still show *something* when offline (Section 6 of the blueprint).
CREATE TABLE IF NOT EXISTS risk_cache (
    segment_id      TEXT PRIMARY KEY,
    risk_level      TEXT NOT NULL,        -- Low / Medium / High
    risk_score      REAL,                 -- raw 0-1 probability
    last_updated    TEXT NOT NULL         -- ISO timestamp — shown
                                           -- in UI as "last updated
                                           -- X hours ago" when offline
);

-- Queue table driving the background sync service (Week 4).
-- Kept separate from hazard_reports so retry logic/backoff can
-- live here without cluttering the report data itself.
CREATE TABLE IF NOT EXISTS sync_queue (
    queue_id        INTEGER PRIMARY KEY AUTOINCREMENT,
    report_id       TEXT NOT NULL REFERENCES hazard_reports(report_id),
    attempt_count   INTEGER NOT NULL DEFAULT 0,
    last_attempt_at TEXT,
    next_retry_at   TEXT
);

-- Helpful index for the sync service's main query:
-- "give me all reports still pending sync"
CREATE INDEX IF NOT EXISTS idx_reports_pending
    ON hazard_reports (sync_status);