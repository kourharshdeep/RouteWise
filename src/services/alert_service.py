"""Alert and Monitoring Service.

Honest Framing & Constraints:
- RouteWise alerts are strictly IN-APP advisories. No SMS, push notifications, or cellular broadcast daemons exist.
- De-duplication enforces a 1-hour cooldown: no two active alerts for the same (segment_id, alert_type).
- High-risk advisory alerts automatically clear when segment risk drops below the 0.35 threshold.
- Road closure alerts automatically clear when all blocking hazard disruptions on that segment are resolved.
- Role-based permissions: public read for commuters/guests; alert acknowledgement and manual clearing
  are restricted exclusively to Patrol officers and Administrators.
- Stored exclusively in the runtime SQLite database (data/runtime/routewise_live.db).
"""
from __future__ import annotations

import logging
import sqlite3
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from fastapi import HTTPException, status

from src.api.schemas.alerts import IN_APP_DELIVERY_NOTICE
from src.services.weather.storage import WeatherStorage, weather_storage

logger = logging.getLogger("alert_service")

# Cooldown duration in seconds (1 hour)
ALERT_COOLDOWN_SECONDS = 3600

# Fixed Bilingual Notification Templates (English + Hindi Unreviewed)
ALERT_TEMPLATES = {
    "closure": {
        "severity": "critical",
        "title_en": "Corridor Segment Closure",
        "title_hi": "गलियारा खंड पूर्णतः बंद",
        "message_en": "Segment {segment_id} is CLOSED due to active hazard disruption. Single mountain road has no bypass; hold or delay transit.",
        "message_hi": "सक्रिय खतरे के कारण खंड {segment_id} बंद है। एकल पहाड़ी मार्ग पर कोई बाईपास नहीं है; यात्रा रोकें या प्रतीक्षा करें।",
    },
    "high_risk": {
        "severity": "warning",
        "title_en": "High Landslide Risk Advisory",
        "title_hi": "उच्च भूस्खलन जोखिम सलाह",
        "message_en": "Segment {segment_id} advisory risk score is {score_pct}%. Heightened susceptibility to rockfall and slope instability.",
        "message_hi": "खंड {segment_id} का सलाहकारी जोखिम स्कोर {score_pct}% है। पत्थर गिरने और ढलान अस्थिरता की संवेदनशीलता अधिक है।",
    },
    "hazard_disruption": {
        "severity": "warning",
        "title_en": "Active Hazard Disruption",
        "title_hi": "सक्रिय खतरा व्यवधान",
        "message_en": "Active {hazard_type} reported on segment {segment_id}. Exercise heightened driving caution.",
        "message_hi": "खंड {segment_id} पर सक्रिय {hazard_type} दर्ज। वाहन चलाते समय अतिरिक्त सावधानी बरतें।",
    },
    "weather_warning": {
        "severity": "advisory",
        "title_en": "Severe Weather Warning",
        "title_hi": "गंभीर मौसम चेतावनी",
        "message_en": "Intense cumulative rainfall ({precip_mm} mm) observed along segment {segment_id}.",
        "message_hi": "खंड {segment_id} पर भारी संचयी वर्षा ({precip_mm} मिमी) दर्ज की गई।",
    },
    "telemetry_stale": {
        "severity": "advisory",
        "title_en": "Stale Telemetry Advisory",
        "title_hi": "बासी टेलीमेट्री सलाह",
        "message_en": "Telemetry for segment {segment_id} exceeds 24 hours. Status is unmonitored UNKNOWN.",
        "message_hi": "खंड {segment_id} की टेलीमेट्री 24 घंटे से अधिक पुरानी है। स्थिति अप्रमाणित अज्ञात है।",
    },
}

# Multi-Day Storm Scenario Presets for Demo Replay Mode (July 2023 Monsoon Event)
SCENARIO_STEPS = [
    {
        "step": 0,
        "date": "2023-07-06",
        "phase": "Baseline Clear",
        "title": "Normal Operational Baseline",
        "description": "Clear mountain weather conditions. All corridor segments open with low baseline risk.",
        "simulated_hazard": None,
    },
    {
        "step": 1,
        "date": "2023-07-07",
        "phase": "Storm Approach",
        "title": "Approaching Monsoon Depression",
        "description": "Initial precipitation onset across Ramban district. Weather advisories begin accumulating.",
        "simulated_hazard": None,
    },
    {
        "step": 2,
        "date": "2023-07-08",
        "phase": "Severe Rainfall",
        "title": "Continuous Mountain Downpour",
        "description": "Heavy monsoon rainfall saturating slopes. High risk advisories trigger across vulnerable cliffs.",
        "simulated_hazard": None,
    },
    {
        "step": 3,
        "date": "2023-07-09",
        "phase": "Peak Cloudburst & Obstruction",
        "title": "Cloudburst & Cafeteria Morh Landslide",
        "description": "Peak torrential cloudburst triggers shooting stones and debris blocking Cafeteria Morh. Corridor status turns CLOSED with mandatory HOLD recommendation.",
        "simulated_hazard": {
            "preset": "landslide",
            "segment_id": "2477017966_12734157829_0",
            "severity": "critical",
            "duration_hours": 24,
        },
    },
    {
        "step": 4,
        "date": "2023-07-10",
        "phase": "Post-Storm Clearance",
        "title": "Post-Storm Clearance & Recovery",
        "description": "Rain subsides and emergency road clearance completes. Closure alerts auto-clear and highway returns to Caution/Proceed status.",
        "simulated_hazard": None,
    },
]


class AlertService:
    """Manages alert lifecycle, cooldown de-duplication, auto-clearance, and replay scenarios."""

    def __init__(self, storage: Optional[WeatherStorage] = None) -> None:
        self.storage = storage or weather_storage

    def _get_connection(self) -> sqlite3.Connection:
        self.storage.db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(self.storage.db_path))
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode = WAL;")
        conn.execute("PRAGMA synchronous = NORMAL;")
        return conn

    def init_db(self) -> None:
        """Initializes the alert table and required indexes in the runtime database."""
        with self._get_connection() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS alert (
                    id TEXT PRIMARY KEY,
                    segment_id TEXT NOT NULL,
                    alert_type TEXT NOT NULL,
                    severity TEXT NOT NULL,
                    title_en TEXT NOT NULL,
                    title_hi TEXT NOT NULL,
                    message_en TEXT NOT NULL,
                    message_hi TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'active',
                    is_simulated INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    acknowledged_at TEXT,
                    acknowledged_by INTEGER,
                    cleared_at TEXT
                );
                """
            )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_alert_status ON alert(status);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_alert_seg_type ON alert(segment_id, alert_type, status);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_alert_created ON alert(created_at);")
            conn.commit()

    def should_create_alert(
        self,
        segment_id: str,
        alert_type: str,
        now_dt: Optional[datetime] = None,
    ) -> bool:
        """Enforces de-duplication and 1-hour cooldown rules."""
        self.init_db()
        now = now_dt or datetime.now(timezone.utc)

        with self._get_connection() as conn:
            row = conn.execute(
                """
                SELECT id, status, created_at, cleared_at
                FROM alert
                WHERE segment_id = ? AND alert_type = ?
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (segment_id, alert_type),
            ).fetchone()

            if not row:
                return True

            st = row["status"]
            # Rule 1: No two active or acknowledged alerts for the same (segment_id, alert_type)
            if st in ("active", "acknowledged"):
                return False

            # Rule 2: 1-hour cooldown from most recent alert event (cleared_at or created_at)
            ts_str = row["cleared_at"] or row["created_at"]
            try:
                ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
                if ts.tzinfo is None:
                    ts = ts.replace(tzinfo=timezone.utc)
                elapsed = (now - ts).total_seconds()
                if elapsed < ALERT_COOLDOWN_SECONDS:
                    return False
            except Exception:
                pass

            return True

    def create_alert(
        self,
        segment_id: str,
        alert_type: str,
        severity: Optional[str] = None,
        title_en: Optional[str] = None,
        title_hi: Optional[str] = None,
        message_en: Optional[str] = None,
        message_hi: Optional[str] = None,
        template_kwargs: Optional[Dict[str, Any]] = None,
        is_simulated: bool = False,
        now_dt: Optional[datetime] = None,
    ) -> Optional[Dict[str, Any]]:
        """Creates an alert with bilingual templates if not blocked by de-duplication or cooldown."""
        self.init_db()
        now = now_dt or datetime.now(timezone.utc)
        now_iso = now.isoformat()

        if not self.should_create_alert(segment_id, alert_type, now):
            return None

        tmpl = ALERT_TEMPLATES.get(alert_type, {})
        eff_severity = severity or tmpl.get("severity", "warning")

        kwargs = template_kwargs or {}
        kwargs.setdefault("segment_id", segment_id)
        kwargs.setdefault("score_pct", "35.0")
        kwargs.setdefault("hazard_type", "hazard")
        kwargs.setdefault("precip_mm", "25.0")

        eff_title_en = title_en or tmpl.get("title_en", f"Advisory for {segment_id}")
        eff_title_hi = title_hi or tmpl.get("title_hi", f"{segment_id} के लिए सलाह")

        msg_en_tmpl = message_en or tmpl.get("message_en", "Advisory detected for segment {segment_id}.")
        msg_hi_tmpl = message_hi or tmpl.get("message_hi", "खंड {segment_id} के लिए सलाह दर्ज की गई।")

        try:
            eff_msg_en = msg_en_tmpl.format(**kwargs)
        except Exception:
            eff_msg_en = msg_en_tmpl

        try:
            eff_msg_hi = msg_hi_tmpl.format(**kwargs)
        except Exception:
            eff_msg_hi = msg_hi_tmpl

        alert_id = str(uuid.uuid4())

        with self._get_connection() as conn:
            conn.execute(
                """
                INSERT INTO alert (
                    id, segment_id, alert_type, severity, title_en, title_hi,
                    message_en, message_hi, status, is_simulated, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'active', ?, ?)
                """,
                (
                    alert_id,
                    segment_id,
                    alert_type,
                    eff_severity,
                    eff_title_en,
                    eff_title_hi,
                    eff_msg_en,
                    eff_msg_hi,
                    1 if is_simulated else 0,
                    now_iso,
                ),
            )
            conn.commit()

        alert_record = {
            "id": alert_id,
            "segment_id": segment_id,
            "alert_type": alert_type,
            "severity": eff_severity,
            "title_en": eff_title_en,
            "title_hi": eff_title_hi,
            "message_en": eff_msg_en,
            "message_hi": eff_msg_hi,
            "status": "active",
            "is_simulated": is_simulated,
            "created_at": now_iso,
            "acknowledged_at": None,
            "acknowledged_by": None,
            "cleared_at": None,
            "delivery_channel": "in_app_only",
            "delivery_notice": IN_APP_DELIVERY_NOTICE,
        }

        # Dispatch SSE broadcast
        try:
            from src.services.live_broadcast_service import live_broadcaster
            live_broadcaster.broadcast_sync("alert", {
                "action": "created",
                "alert": alert_record,
            })
        except Exception as e:
            logger.debug("Failed to dispatch SSE broadcast for alert creation: %s", e)

        return alert_record

    def auto_clear_alerts(
        self,
        segment_id: str,
        alert_type: str,
        now_dt: Optional[datetime] = None,
    ) -> int:
        """Auto-clears active or acknowledged alerts when the triggering condition ceases."""
        self.init_db()
        now = now_dt or datetime.now(timezone.utc)
        now_iso = now.isoformat()

        with self._get_connection() as conn:
            rows = conn.execute(
                """
                SELECT id FROM alert
                WHERE segment_id = ? AND alert_type = ? AND status IN ('active', 'acknowledged')
                """,
                (segment_id, alert_type),
            ).fetchall()

            if not rows:
                return 0

            conn.execute(
                """
                UPDATE alert
                SET status = 'cleared', cleared_at = ?
                WHERE segment_id = ? AND alert_type = ? AND status IN ('active', 'acknowledged')
                """,
                (now_iso, segment_id, alert_type),
            )
            conn.commit()

        # Dispatch SSE notification
        try:
            from src.services.live_broadcast_service import live_broadcaster
            for r in rows:
                live_broadcaster.broadcast_sync("alert", {
                    "action": "cleared",
                    "alert_id": r["id"],
                    "segment_id": segment_id,
                    "alert_type": alert_type,
                    "cleared_at": now_iso,
                })
        except Exception as e:
            logger.debug("Failed to broadcast alert auto-clear: %s", e)

        return len(rows)

    def sync_alerts_from_live_state(
        self,
        live_risk_payload: Optional[Dict[str, Any]] = None,
        active_events: Optional[List[Dict[str, Any]]] = None,
        now_dt: Optional[datetime] = None,
    ) -> Dict[str, int]:
        """Synchronizes alerts with live risk scores and active hazard events."""
        self.init_db()
        now = now_dt or datetime.now(timezone.utc)

        if live_risk_payload is None:
            from src.services.live_risk_service import live_risk_service
            live_risk_payload = live_risk_service.get_latest_live_risk()

        if active_events is None:
            from src.services.hazard_event_service import hazard_event_service
            active_events = hazard_event_service.get_active_events()

        events_by_seg: Dict[str, List[Dict[str, Any]]] = {}
        for ev in active_events:
            events_by_seg.setdefault(ev["segment_id"], []).append(ev)

        if isinstance(live_risk_payload, list):
            segments = live_risk_payload
        elif isinstance(live_risk_payload, dict):
            segments = live_risk_payload.get("segments", [])
        else:
            segments = []

        created_count = 0
        cleared_count = 0

        for seg in segments:
            sid = seg["segment_id"] if isinstance(seg, dict) else getattr(seg, "segment_id", None)
            if not sid:
                continue
            score = seg.get("risk_score") if isinstance(seg, dict) else getattr(seg, "risk_score", None)
            op_status = seg.get("operational_status", "OPEN") if isinstance(seg, dict) else getattr(seg, "operational_status", "OPEN")
            is_sim = seg.get("has_simulated_event", False) if isinstance(seg, dict) else getattr(seg, "has_simulated_event", False)
            seg_events = events_by_seg.get(sid, [])

            # 1. Road Closure Alert
            is_closed = op_status == "CLOSED" or any(ev["severity"] == "critical" and ev["status"] == "active" for ev in seg_events)
            if is_closed:
                res = self.create_alert(
                    segment_id=sid,
                    alert_type="closure",
                    severity="critical",
                    is_simulated=is_sim,
                    now_dt=now,
                )
                if res:
                    created_count += 1
            else:
                cleared_count += self.auto_clear_alerts(sid, "closure", now)

            # 2. High Risk Score Alert
            if score is not None and score >= 0.35:
                res = self.create_alert(
                    segment_id=sid,
                    alert_type="high_risk",
                    severity="critical" if score >= 0.50 else "warning",
                    template_kwargs={"score_pct": f"{score * 100:.1f}"},
                    is_simulated=is_sim,
                    now_dt=now,
                )
                if res:
                    created_count += 1
            else:
                cleared_count += self.auto_clear_alerts(sid, "high_risk", now)

            # 3. Hazard Disruption Alert
            non_closure_hazards = [ev for ev in seg_events if ev.get("severity") in ("high", "medium")]
            if non_closure_hazards:
                primary_hazard = non_closure_hazards[0].get("hazard_type", "hazard")
                res = self.create_alert(
                    segment_id=sid,
                    alert_type="hazard_disruption",
                    severity="warning",
                    template_kwargs={"hazard_type": primary_hazard.replace("_", " ")},
                    is_simulated=is_sim,
                    now_dt=now,
                )
                if res:
                    created_count += 1
            else:
                cleared_count += self.auto_clear_alerts(sid, "hazard_disruption", now)

        return {"created": created_count, "cleared": cleared_count}

    def acknowledge_alert(
        self,
        alert_id: str,
        user_id: int,
        now_dt: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        """Marks an active alert as acknowledged by a patrol officer."""
        self.init_db()
        now = now_dt or datetime.now(timezone.utc)
        now_iso = now.isoformat()

        with self._get_connection() as conn:
            row = conn.execute("SELECT * FROM alert WHERE id = ?", (alert_id,)).fetchone()
            if not row:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Alert '{alert_id}' not found.",
                )

            if row["status"] == "cleared":
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Alert '{alert_id}' has already been cleared.",
                )

            conn.execute(
                """
                UPDATE alert
                SET status = 'acknowledged', acknowledged_at = ?, acknowledged_by = ?
                WHERE id = ?
                """,
                (now_iso, user_id, alert_id),
            )
            conn.commit()

        # Broadcast SSE notification
        try:
            from src.services.live_broadcast_service import live_broadcaster
            live_broadcaster.broadcast_sync("alert", {
                "action": "acknowledged",
                "alert_id": alert_id,
                "acknowledged_at": now_iso,
                "acknowledged_by": user_id,
            })
        except Exception as e:
            logger.debug("Failed to broadcast alert acknowledgement: %s", e)

        return {
            "id": alert_id,
            "status": "acknowledged",
            "acknowledged_at": now_iso,
            "acknowledged_by": user_id,
        }

    def clear_alert(
        self,
        alert_id: str,
        user_id: Optional[int] = None,
        now_dt: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        """Manually clears an alert (Patrol or Admin only)."""
        self.init_db()
        now = now_dt or datetime.now(timezone.utc)
        now_iso = now.isoformat()

        with self._get_connection() as conn:
            row = conn.execute("SELECT * FROM alert WHERE id = ?", (alert_id,)).fetchone()
            if not row:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Alert '{alert_id}' not found.",
                )

            conn.execute(
                """
                UPDATE alert
                SET status = 'cleared', cleared_at = ?
                WHERE id = ?
                """,
                (now_iso, alert_id),
            )
            conn.commit()

        # Broadcast SSE notification
        try:
            from src.services.live_broadcast_service import live_broadcaster
            live_broadcaster.broadcast_sync("alert", {
                "action": "cleared",
                "alert_id": alert_id,
                "cleared_at": now_iso,
                "cleared_by": user_id,
            })
        except Exception as e:
            logger.debug("Failed to broadcast manual alert clear: %s", e)

        return {
            "id": alert_id,
            "status": "cleared",
            "cleared_at": now_iso,
        }

    def clear_all_alerts(self) -> int:
        """Removes all alert records (useful for test isolation and scenario reset)."""
        self.init_db()
        with self._get_connection() as conn:
            deleted = conn.execute("DELETE FROM alert").rowcount
            conn.commit()
            return deleted

    def get_active_alerts(self, limit: int = 100) -> List[Dict[str, Any]]:
        """Retrieves active and acknowledged alerts sorted by severity and recency."""
        self.init_db()
        with self._get_connection() as conn:
            rows = conn.execute(
                """
                SELECT * FROM alert
                WHERE status IN ('active', 'acknowledged')
                ORDER BY
                    CASE severity
                        WHEN 'critical' THEN 1
                        WHEN 'warning' THEN 2
                        WHEN 'advisory' THEN 3
                        ELSE 4
                    END ASC,
                    created_at DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()

            return [self._format_alert(dict(r)) for r in rows]

    def get_alert_history(self, limit: int = 100) -> List[Dict[str, Any]]:
        """Retrieves alert audit history including cleared alerts."""
        self.init_db()
        with self._get_connection() as conn:
            rows = conn.execute(
                "SELECT * FROM alert ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
            return [self._format_alert(dict(r)) for r in rows]

    def _format_alert(self, d: Dict[str, Any]) -> Dict[str, Any]:
        """Formats an alert dictionary and injects in-app delivery boundary metadata."""
        d["is_simulated"] = bool(d.get("is_simulated", 0))
        d["delivery_channel"] = "in_app_only"
        d["delivery_notice"] = IN_APP_DELIVERY_NOTICE
        return d

    def step_replay_scenario(self, step_index: int, user_id: Optional[int] = None) -> Dict[str, Any]:
        """Executes a step in the multi-day storm demonstration scenario (July 2023 Monsoon Event)."""
        if step_index < 0 or step_index >= len(SCENARIO_STEPS):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid scenario step_index {step_index}. Valid indices: 0 to {len(SCENARIO_STEPS) - 1}.",
            )

        step_cfg = SCENARIO_STEPS[step_index]
        target_date = step_cfg["date"]

        # 1. Ingest historical weather replay observations for the target window
        from src.services.weather.replay import ReplayProvider
        from src.services.weather.storage import weather_storage
        from src.services.live_risk_service import live_risk_service
        from src.services.hazard_event_service import hazard_event_service
        from src.services.journey_service import journey_service

        replay_prov = ReplayProvider()
        target_dt = datetime.strptime(target_date, "%Y-%m-%d").date()
        start_dt = target_dt - timedelta(days=7)
        df = replay_prov.fetch(start_date=start_dt, end_date=target_dt)
        if not df.empty:
            weather_storage.upsert_observations(df)

        # 2. Handle simulated hazard overlay
        if step_cfg["simulated_hazard"]:
            sim = step_cfg["simulated_hazard"]
            hazard_event_service.simulate_event(
                preset=sim["preset"],
                segment_id=sim["segment_id"],
                severity=sim["severity"],
                duration_hours=sim["duration_hours"],
                user_id=user_id,
            )
        else:
            # Clear previous simulated events when transitioning to clear phases
            hazard_event_service.clear_all_simulated_events(user_id=user_id)

        # 3. Compute live risk for target date (eval time matches replay scenario)
        scenario_eval_time = datetime.strptime(target_date, "%Y-%m-%d").replace(tzinfo=timezone.utc) + timedelta(hours=12)
        live_risk = live_risk_service.compute_live_risk(as_of=target_date, eval_time=scenario_eval_time)

        # 4. Synchronize alerts with current corridor state
        self.sync_alerts_from_live_state(live_risk_payload=live_risk)

        # 5. Evaluate journey planner route recommendation on corridor
        from src.api.schemas.journey import JourneyPlanRequest
        plan_req = JourneyPlanRequest(
            origin="Ramban Gateway",
            destination="Banihal Gateway",
            mode="live",
            date=target_date,
        )
        plan_res = journey_service.plan_journey(plan_req)

        active_alerts = self.get_active_alerts()
        op_status = plan_res.overall_route_risk

        return {
            "step": step_index,
            "date": target_date,
            "phase": step_cfg["phase"],
            "title": step_cfg["title"],
            "description": step_cfg["description"],
            "active_alerts_count": len(active_alerts),
            "alerts": active_alerts,
            "corridor_operational_status": plan_res.overall_route_risk,
            "route_recommendation": plan_res.recommendation,
            "route_recommendation_reason": plan_res.recommendation_reason,
            "is_simulated": True,
            "delivery_channel": "in_app_only",
        }


# Global singleton instance
alert_service = AlertService()
