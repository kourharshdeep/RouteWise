"""Hazard Event Management & Operational Status Overlay Service.

Honest Framing:
- Hazard events (field reports, operator simulations, official advisories) are an OPERATIONAL OVERLAY.
- They NEVER alter model weights, input features, or model inference scores.
- Any event originating from simulation is strictly badged 'is_simulated=True' ('SIMULATED').
- Simulated events are stored exclusively in the runtime database (data/runtime/routewise_live.db)
  and NEVER enter historical training tables or datasets.
- Unverified field reports (status 'submitted') NEVER generate public events.
"""
from __future__ import annotations

import contextlib
import logging
import sqlite3
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from fastapi import HTTPException, status

from src.api.config import settings
from src.services.weather.storage import WeatherStorage, weather_storage

logger = logging.getLogger("hazard_event_service")

# Permitted simulation hazard presets
VALID_PRESETS = {
    "landslide": {"severity": "critical", "default_duration_hours": 24},
    "shooting_stones": {"severity": "high", "default_duration_hours": 12},
    "snow_ice": {"severity": "high", "default_duration_hours": 18},
    "flooding": {"severity": "critical", "default_duration_hours": 12},
    "road_damage": {"severity": "medium", "default_duration_hours": 48},
    "single_lane": {"severity": "medium", "default_duration_hours": 36},
}


def _has_table(conn: sqlite3.Connection, name: str) -> bool:
    """Checks whether a table exists in the database schema."""
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name = ?",
        (name,),
    ).fetchone()
    return row is not None


class HazardEventService:
    """Manages active hazard events, auto-expiry audit trails, and derived operational status."""

    def __init__(self, storage: Optional[WeatherStorage] = None) -> None:
        self.storage = storage or weather_storage
        self._initialized_dbs: set[Path] = set()
        self._active_events_cache: Dict[bool, List[Dict[str, Any]]] = {}
        self._cache_earliest_expires_at: Dict[bool, Optional[str]] = {}

    def invalidate_cache(self) -> None:
        """Invalidates in-memory active hazard events cache."""
        self._active_events_cache.clear()
        self._cache_earliest_expires_at.clear()

    def reset_db_init(self) -> None:
        """Clears DB initialization tracking for tests."""
        self._initialized_dbs.clear()
        self._active_events_cache.clear()
        self._cache_earliest_expires_at.clear()

    def _get_connection(self) -> sqlite3.Connection:
        self.storage.db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(self.storage.db_path))
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode = WAL;")
        conn.execute("PRAGMA synchronous = NORMAL;")
        return conn

    def init_db(self) -> None:
        """Initializes hazard_event and hazard_event_history tables."""
        db_path = self.storage.db_path
        if db_path in self._initialized_dbs and db_path.is_file():
            try:
                with contextlib.closing(sqlite3.connect(str(db_path))) as conn:
                    if conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='hazard_event'").fetchone():
                        return
            except Exception:
                pass
            self._initialized_dbs.discard(db_path)

        with contextlib.closing(self._get_connection()) as conn:
            with conn:
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS hazard_event (
                        id TEXT PRIMARY KEY,
                        segment_id TEXT NOT NULL,
                        hazard_type TEXT NOT NULL,
                        severity TEXT NOT NULL,
                        status TEXT NOT NULL DEFAULT 'active',
                        origin TEXT NOT NULL,
                        is_simulated INTEGER NOT NULL DEFAULT 0,
                        source_report_id TEXT,
                        report_count INTEGER NOT NULL DEFAULT 1,
                        last_reported_at TEXT,
                        starts_at TEXT NOT NULL,
                        expires_at TEXT NOT NULL,
                        created_by INTEGER,
                        created_at TEXT NOT NULL
                    );
                    """
                )
                conn.execute("CREATE INDEX IF NOT EXISTS idx_hazard_event_seg ON hazard_event(segment_id, status);")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_hazard_event_status ON hazard_event(status, expires_at);")
                cols = {c[1] for c in conn.execute("PRAGMA table_info(hazard_event)").fetchall()}
                if "is_simulated" in cols:
                    conn.execute("CREATE INDEX IF NOT EXISTS idx_hazard_event_sim ON hazard_event(is_simulated);")
                if "source_report_id" in cols:
                    conn.execute("CREATE INDEX IF NOT EXISTS idx_hazard_event_report ON hazard_event(source_report_id);")
                if "report_count" not in cols:
                    conn.execute("ALTER TABLE hazard_event ADD COLUMN report_count INTEGER NOT NULL DEFAULT 1;")
                if "last_reported_at" not in cols:
                    conn.execute("ALTER TABLE hazard_event ADD COLUMN last_reported_at TEXT;")
                    conn.execute("UPDATE hazard_event SET last_reported_at = created_at WHERE last_reported_at IS NULL;")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_hazard_event_dedup ON hazard_event(segment_id, hazard_type, status);")

                # Audit trail table for lifecycle actions (create, refresh, close, auto-expire)
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS hazard_event_history (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        event_id TEXT NOT NULL,
                        action TEXT NOT NULL,
                        note TEXT,
                        actor_id INTEGER,
                        timestamp TEXT NOT NULL,
                        FOREIGN KEY(event_id) REFERENCES hazard_event(id) ON DELETE CASCADE
                    );
                    """
                )
                conn.execute("CREATE INDEX IF NOT EXISTS idx_hazard_history_event ON hazard_event_history(event_id);")
        self._initialized_dbs.add(db_path)

    def expire_active_events(self, now: Optional[datetime] = None) -> int:
        """Auto-expires events past their expires_at deadline with an audit trail entry."""
        self.init_db()
        now_iso = (now or datetime.now(timezone.utc)).isoformat()
        with self._get_connection() as conn:
            expired_rows = conn.execute(
                "SELECT id FROM hazard_event WHERE status = 'active' AND expires_at < ?",
                (now_iso,),
            ).fetchall()

            if not expired_rows:
                return 0

            expired_ids = [r["id"] for r in expired_rows]
            for eid in expired_ids:
                conn.execute(
                    "UPDATE hazard_event SET status = 'expired' WHERE id = ?",
                    (eid,),
                )
                conn.execute(
                    """
                    INSERT INTO hazard_event_history (event_id, action, note, actor_id, timestamp)
                    VALUES (?, 'AUTO_EXPIRED', 'Event automatically expired at end of operational validity period', NULL, ?)
                    """,
                    (eid, now_iso),
                )
            conn.commit()
            if expired_ids:
                self.invalidate_cache()
            logger.info("Auto-expired %d overdue hazard events", len(expired_ids))
            return len(expired_ids)

    def on_report_status_change(
        self,
        report_id: str,
        status_value: str,
        category: str,
        segment_id: Optional[str],
        actor_id: Optional[int] = None,
        is_simulated: bool = False,
    ) -> Optional[str]:
        """Handles hazard event lifecycle transitions when a field report's status changes."""
        self.init_db()
        now_iso = datetime.now(timezone.utc).isoformat()

        # Unverified reports (status 'submitted') NEVER create public events
        if status_value == "submitted":
            return None

        # Severity ranking for "severity is never lowered"
        SEVERITY_RANK = {"low": 1, "medium": 2, "high": 3, "critical": 4}

        # Resolved or rejected reports close existing active events
        if status_value in ("resolved", "rejected"):
            with self._get_connection() as conn:
                has_reports = _has_table(conn, "reports")
                existing = conn.execute(
                    "SELECT id, source_report_id FROM hazard_event WHERE source_report_id = ? AND status = 'active'",
                    (report_id,),
                ).fetchall()
                for r in existing:
                    eid = r["id"]
                    conn.execute(
                        "UPDATE hazard_event SET status = 'closed' WHERE id = ?",
                        (eid,),
                    )
                    conn.execute(
                        """
                        INSERT INTO hazard_event_history (event_id, action, note, actor_id, timestamp)
                        VALUES (?, 'CLOSED', ?, ?, ?)
                        """,
                        (eid, f"Field report transitioned to {status_value}", actor_id, now_iso),
                    )
                    if status_value == "resolved":
                        if has_reports:
                            conn.execute(
                                """
                                UPDATE reports
                                SET status = 'resolved', updated_at = ?
                                WHERE (hazard_event_id = ? OR (duplicate_of IS NOT NULL AND duplicate_of = ?))
                                  AND status IN ('submitted', 'verified', 'assigned')
                                """,
                                (now_iso, eid, r["source_report_id"] or report_id),
                            )
                conn.commit()
            if existing:
                self._broadcast_event_change("close", existing[0]["id"])
            return None

        # Verified or assigned reports create or refresh active event
        if status_value in ("verified", "assigned"):
            if not segment_id:
                logger.warning("Cannot create hazard event for report %s: no segment_id attached.", report_id)
                return None

            # Map category to standardized hazard_type without collapsing unmapped types
            cat_norm = category.lower().replace(" ", "_").replace("-", "_")
            hazard_type = cat_norm if cat_norm in VALID_PRESETS else "road_damage"
            severity = VALID_PRESETS.get(hazard_type, {}).get("severity", "critical" if hazard_type in ("landslide", "flooding") else "medium")
            expires_at = (datetime.now(timezone.utc) + timedelta(hours=24)).isoformat()
            sim_val = 1 if is_simulated else 0
            dedup_hours = getattr(settings, "dedup_window_hours", 24.0)
            dedup_window_start = (datetime.now(timezone.utc) - timedelta(hours=dedup_hours)).isoformat()

            with self._get_connection() as conn:
                has_reports = _has_table(conn, "reports")
                existing = conn.execute(
                    """
                    SELECT id, severity, report_count, last_reported_at, source_report_id, expires_at
                    FROM hazard_event
                    WHERE source_report_id = ? AND status = 'active'
                    """,
                    (report_id,),
                ).fetchone()

                if not existing:
                    # Look for duplicate active event on the same segment considering created_at and last_reported_at
                    existing = conn.execute(
                        """
                        SELECT id, severity, report_count, last_reported_at, source_report_id, expires_at
                        FROM hazard_event
                        WHERE segment_id = ?
                          AND hazard_type = ?
                          AND COALESCE(is_simulated, 0) = ?
                          AND status = 'active'
                          AND expires_at > ?
                          AND (created_at >= ? OR (last_reported_at IS NOT NULL AND last_reported_at >= ?))
                        ORDER BY created_at ASC
                        LIMIT 1
                        """,
                        (segment_id, hazard_type, sim_val, now_iso, dedup_window_start, dedup_window_start),
                    ).fetchone()

                if existing:
                    event_id = existing["id"]
                    is_same_source = (existing["source_report_id"] == report_id)

                    if is_same_source:
                        if status_value == "verified":
                            conn.execute(
                                "UPDATE hazard_event SET expires_at = ?, status = 'active' WHERE id = ?",
                                (expires_at, event_id),
                            )
                        else:
                            conn.execute(
                                "UPDATE hazard_event SET status = 'active' WHERE id = ?",
                                (event_id,),
                            )
                        conn.execute(
                            """
                            INSERT INTO hazard_event_history (event_id, action, note, actor_id, timestamp)
                            VALUES (?, 'REFRESHED', ?, ?, ?)
                            """,
                            (event_id, f"Refreshed due to report status {status_value}", actor_id, now_iso),
                        )
                        action = "refresh"
                    else:
                        cur_reporter_id = None
                        report_created_at = now_iso
                        is_already_linked = False

                        if has_reports:
                            cur_rep = conn.execute(
                                "SELECT reporter_id, created_at, hazard_event_id FROM reports WHERE id = ?",
                                (report_id,),
                            ).fetchone()
                            if cur_rep:
                                cur_reporter_id = cur_rep["reporter_id"]
                                report_created_at = cur_rep["created_at"] or now_iso
                        # Guest / anonymous report rule: reporter_id None or <= 0 is not an independent verified reporter
                        is_independent = False
                        if status_value == "verified":
                            if cur_reporter_id is not None and cur_reporter_id > 0:
                                existing_reporters = set()
                                if has_reports:
                                    rep_rows = conn.execute(
                                        """
                                        SELECT reporter_id FROM reports
                                        WHERE (hazard_event_id = ? OR (duplicate_of IS NOT NULL AND duplicate_of = ?) OR id = ?)
                                          AND id != ?
                                          AND status IN ('verified', 'assigned', 'resolved')
                                          AND reporter_id IS NOT NULL
                                        """,
                                        (event_id, existing["source_report_id"], existing["source_report_id"], report_id),
                                    ).fetchall()
                                    for rr in rep_rows:
                                        if rr["reporter_id"] is not None and rr["reporter_id"] > 0:
                                            existing_reporters.add(rr["reporter_id"])
                                is_independent = (cur_reporter_id not in existing_reporters)
                            elif not has_reports and not is_same_source:
                                # In legacy schemas without reports table, each distinct report_id counts once
                                is_independent = True

                        cur_count = int(existing["report_count"]) if existing["report_count"] is not None else 1
                        new_count = cur_count + (1 if is_independent else 0)

                        old_sev = existing["severity"]
                        if SEVERITY_RANK.get(severity, 0) > SEVERITY_RANK.get(old_sev, 0):
                            new_sev = severity
                        else:
                            new_sev = old_sev

                        if status_value == "verified":
                            new_last_rep = max(existing["last_reported_at"] or now_iso, report_created_at or now_iso)
                            new_expires = max(existing["expires_at"], expires_at)
                        else:
                            new_last_rep = existing["last_reported_at"]
                            new_expires = existing["expires_at"]


                        conn.execute(
                            """
                            UPDATE hazard_event
                            SET report_count = ?,
                                last_reported_at = ?,
                                severity = ?,
                                expires_at = ?,
                                status = 'active'
                            WHERE id = ?
                            """,
                            (new_count, new_last_rep, new_sev, new_expires, event_id),
                        )

                        if has_reports:
                            conn.execute(
                                """
                                UPDATE reports
                                SET duplicate_of = ?,
                                    hazard_event_id = ?
                                WHERE id = ?
                                """,
                                (existing["source_report_id"] if existing["source_report_id"] else None, event_id, report_id),
                            )

                        conn.execute(
                            """
                            INSERT INTO hazard_event_history (event_id, action, note, actor_id, timestamp)
                            VALUES (?, 'REPORT_LINKED', ?, ?, ?)
                            """,
                            (
                                event_id,
                                f"Report {report_id} linked (independent={is_independent}, count={new_count}, severity={new_sev})",
                                actor_id,
                                now_iso,
                            ),
                        )
                        action = "refresh"
                else:
                    event_id = str(uuid.uuid4())
                    rep_time = now_iso
                    if has_reports:
                        cur_rep = conn.execute(
                            "SELECT created_at FROM reports WHERE id = ?",
                            (report_id,),
                        ).fetchone()
                        if cur_rep and cur_rep["created_at"]:
                            rep_time = cur_rep["created_at"]

                    conn.execute(
                        """
                        INSERT INTO hazard_event (
                            id, segment_id, hazard_type, severity, status, origin,
                            is_simulated, source_report_id, report_count, last_reported_at,
                            starts_at, expires_at, created_by, created_at
                        ) VALUES (?, ?, ?, ?, 'active', 'field_report', ?, ?, 1, ?, ?, ?, ?, ?)
                        """,
                        (
                            event_id,
                            segment_id,
                            hazard_type,
                            severity,
                            sim_val,
                            report_id,
                            rep_time,
                            now_iso,
                            expires_at,
                            actor_id,
                            now_iso,
                        ),
                    )
                    if has_reports:
                        conn.execute(
                            """
                            UPDATE reports
                            SET hazard_event_id = ?, duplicate_of = NULL
                            WHERE id = ?
                            """,
                            (event_id, report_id),
                        )

                    conn.execute(
                        """
                        INSERT INTO hazard_event_history (event_id, action, note, actor_id, timestamp)
                        VALUES (?, 'CREATED', 'Created from verified field report', ?, ?)
                        """,
                        (event_id, actor_id, now_iso),
                    )
                    action = "create"

                conn.commit()
            self._broadcast_event_change(action, event_id)
            return event_id

        return None

    def _broadcast_event_change(self, action: str, event_id: Optional[str] = None, now: Optional[datetime] = None) -> None:
        """Dispatches an SSE event notification and updated live risk payload."""
        self.invalidate_cache()
        try:
            from src.services.live_broadcast_service import live_broadcaster
            effective_now = now or datetime.now(timezone.utc)
            live_broadcaster.broadcast_sync("event_update", {
                "action": action,
                "event_id": event_id,
            })
            live_broadcaster.broadcast_sync("route_update", {
                "reason": f"hazard_{action}",
                "event_id": event_id,
                "timestamp": effective_now.isoformat(),
            })
            from src.services.live_risk_service import live_risk_service
            live_broadcaster.broadcast_sync("risk_update", live_risk_service.get_latest_live_risk(eval_time=effective_now))
            live_broadcaster.broadcast_sync("status", live_risk_service.get_live_status())
        except Exception as e:
            logger.debug("Failed to dispatch SSE broadcast for hazard event: %s", e)

    def simulate_event(
        self,
        preset: str,
        segment_id: str,
        severity: Optional[str] = None,
        duration_hours: Optional[int] = None,
        user_id: Optional[int] = None,
        now: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        """Creates an operator-simulated hazard event (Admin only)."""
        self.init_db()
        norm_preset = preset.lower().replace("-", "_").strip()
        if norm_preset not in VALID_PRESETS:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid simulation preset '{preset}'. Valid presets: {sorted(list(VALID_PRESETS.keys()))}",
            )

        preset_cfg = VALID_PRESETS[norm_preset]
        eff_severity = severity or preset_cfg["severity"]
        eff_duration = duration_hours if (duration_hours and duration_hours > 0) else preset_cfg["default_duration_hours"]

        now_dt = now or datetime.now(timezone.utc)
        now_iso = now_dt.isoformat()
        expires_iso = (now_dt + timedelta(hours=eff_duration)).isoformat()
        event_id = str(uuid.uuid4())

        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO hazard_event (
                    id, segment_id, hazard_type, severity, status, origin,
                    is_simulated, source_report_id, report_count, last_reported_at,
                    starts_at, expires_at, created_by, created_at
                ) VALUES (?, ?, ?, ?, 'active', 'simulated', 1, NULL, 1, ?, ?, ?, ?, ?)
                """,
                (
                    event_id,
                    segment_id,
                    norm_preset,
                    eff_severity,
                    now_iso,
                    now_iso,
                    expires_iso,
                    user_id,
                    now_iso,
                ),
            )
            conn.execute(
                """
                INSERT INTO hazard_event_history (event_id, action, note, actor_id, timestamp)
                VALUES (?, 'CREATED', 'Admin operator simulated event initialized', ?, ?)
                """,
                (event_id, user_id, now_iso),
            )
            conn.commit()

        logger.info(
            "Operator simulated event %s (%s, severity: %s) on segment %s (expires: %s)",
            event_id,
            norm_preset,
            eff_severity,
            segment_id,
            expires_iso,
        )

        res = {
            "id": event_id,
            "segment_id": segment_id,
            "hazard_type": norm_preset,
            "severity": eff_severity,
            "status": "active",
            "origin": "simulated",
            "is_simulated": True,
            "badge": "SIMULATED",
            "report_count": 1,
            "last_reported_at": now_iso,
            "starts_at": now_iso,
            "expires_at": expires_iso,
            "created_by": user_id,
            "created_at": now_iso,
        }
        self._broadcast_event_change("simulate", event_id, now=now_dt)
        return res

    def clear_all_simulated_events(self, user_id: Optional[int] = None) -> int:
        """One-action removal of all simulated hazard events."""
        self.init_db()
        now_iso = datetime.now(timezone.utc).isoformat()
        with self._get_connection() as conn:
            sim_rows = conn.execute("SELECT id FROM hazard_event WHERE is_simulated = 1 AND status = 'active'").fetchall()
            for r in sim_rows:
                eid = r["id"]
                conn.execute(
                    "UPDATE hazard_event SET status = 'closed' WHERE id = ?",
                    (eid,),
                )
                conn.execute(
                    """
                    INSERT INTO hazard_event_history (event_id, action, note, actor_id, timestamp)
                    VALUES (?, 'CLOSED', 'Cleared via operator clear-all-simulated action', ?, ?)
                    """,
                    (eid, user_id, now_iso),
                )
            conn.commit()
            logger.info("Cleared %d active simulated events.", len(sim_rows))
            if sim_rows:
                self._broadcast_event_change("clear_simulated")
            return len(sim_rows)

    def get_active_events(
        self,
        segment_id: Optional[str] = None,
        now: Optional[datetime] = None,
        include_simulated: Optional[bool] = None,
    ) -> List[Dict[str, Any]]:
        """Returns active hazard events, auto-expiring overdue items first."""
        effective_now = now or datetime.now(timezone.utc)
        now_iso = effective_now.isoformat()

        inc_sim = (getattr(settings, "live_mode", "live") == "replay") if include_simulated is None else bool(include_simulated)
        cache_key = inc_sim

        if segment_id is None and cache_key in self._active_events_cache:
            earliest_exp = self._cache_earliest_expires_at.get(cache_key)
            if earliest_exp and now_iso >= earliest_exp:
                self.expire_active_events(now=effective_now)
            else:
                return self._active_events_cache[cache_key]

        self.expire_active_events(now=effective_now)
        with self._get_connection() as conn:
            columns = {col[1] for col in conn.execute("PRAGMA table_info(hazard_event)").fetchall()}
            where_clauses = ["status = 'active'"]
            params: List[Any] = []

            if segment_id:
                where_clauses.append("segment_id = ?")
                params.append(segment_id)

            if "is_simulated" in columns and not inc_sim:
                where_clauses.append("COALESCE(is_simulated, 0) = 0")

            where_sql = " AND ".join(where_clauses)
            query = f"SELECT * FROM hazard_event WHERE {where_sql} ORDER BY starts_at DESC"
            rows = conn.execute(query, params).fetchall()

        events = []
        for r in rows:
            is_sim = bool(r["is_simulated"]) if ("is_simulated" in r.keys() and r["is_simulated"] is not None) else False
            rep_count = int(r["report_count"]) if ("report_count" in r.keys() and r["report_count"] is not None) else 1
            last_rep = r["last_reported_at"] if ("last_reported_at" in r.keys() and r["last_reported_at"] is not None) else r["created_at"]
            events.append({
                "id": r["id"],
                "segment_id": r["segment_id"],
                "hazard_type": r["hazard_type"],
                "severity": r["severity"],
                "status": r["status"],
                "origin": r["origin"],
                "is_simulated": is_sim,
                "badge": "SIMULATED" if is_sim else "VERIFIED",
                "source_report_id": r["source_report_id"],
                "report_count": rep_count,
                "last_reported_at": last_rep,
                "starts_at": r["starts_at"],
                "expires_at": r["expires_at"],
                "created_by": r["created_by"],
                "created_at": r["created_at"],
            })
        if segment_id is None:
            self._active_events_cache[cache_key] = events
            self._cache_earliest_expires_at[cache_key] = min((ev["expires_at"] for ev in events), default=None)
        return events

    def get_active_events_by_segment_map(
        self,
        now: Optional[datetime] = None,
        include_simulated: Optional[bool] = None,
    ) -> Dict[str, List[Dict[str, Any]]]:
        """Builds a map of segment_id -> active_events."""
        all_active = self.get_active_events(now=now, include_simulated=include_simulated)
        res: Dict[str, List[Dict[str, Any]]] = {}
        for ev in all_active:
            sid = ev["segment_id"]
            if sid not in res:
                res[sid] = []
            res[sid].append(ev)
        return res

    @staticmethod
    def derive_operational_status(
        model_risk_tier: str,
        active_events: List[Dict[str, Any]],
        model_status: Optional[str] = None,
    ) -> str:
        """Evaluates deterministic operational status rules.
        
        Returns:
            One of 'OPEN' | 'CAUTION' | 'RESTRICTED' | 'CLOSED' | 'UNKNOWN'.
        """
        # 1. Critical physical hazard events force CLOSED regardless of model tier
        has_critical = any(
            ev["severity"] == "critical" or ev["hazard_type"] in ("landslide", "flooding")
            for ev in active_events
        )
        if has_critical:
            return "CLOSED"

        # 2. High severity or single-lane events enforce RESTRICTED
        has_restricted = any(
            ev["hazard_type"] in ("single_lane", "single-lane")
            or ev["severity"] == "high"
            or (ev["hazard_type"] in ("shooting_stones", "snow_ice", "road_damage") and ev["severity"] == "medium")
            for ev in active_events
        )
        if has_restricted:
            return "RESTRICTED"

        # 3. If model input is missing or stale, and no critical/restricted events exist -> UNKNOWN
        if model_risk_tier == "UNKNOWN" or model_status in ("MISSING_DATA", "STALE_DATA"):
            return "UNKNOWN"

        # 4. Active minor events or elevated model risk tier -> CAUTION
        if active_events or model_risk_tier in ("Medium", "High"):
            return "CAUTION"

        # 5. Low risk model score and zero active events -> OPEN
        if model_risk_tier == "Low":
            return "OPEN"

        return "UNKNOWN"


hazard_event_service = HazardEventService()

