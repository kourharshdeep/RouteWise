"""Live Disruption Risk Service for RouteWise.

Honest Framing:
- Evaluates real-time or replayed atmospheric conditions via the trained ST-GNN.
- Live predictions are subject to atmospheric distribution shift and are explicitly
  flagged as "Experimental - not validated".
- Scores represent an advisory relative-risk index, not physical probabilities.
- Never defaults to 'Low' risk: incomplete (<7 days) or stale (>24h) data maps to
  risk_tier='UNKNOWN' and status='MISSING_DATA' or 'STALE_DATA'.
- Bounded 7-day historical retention in isolated runtime DB (data/runtime/routewise_live.db).
"""
from __future__ import annotations

import hashlib
import logging
import sqlite3
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

from src.api.config import settings
from src.models.inference import RiskInferenceEngine, SegmentPrediction
from src.services.weather.base import EXPECTED_DYNAMIC_FEATURES
from src.services.weather.storage import WeatherStorage, weather_storage

logger = logging.getLogger("live_risk_service")

# Expected SHA-256 checksum of stgnn_best.pt
EXPECTED_CHECKPOINT_SHA256 = "68B04504EAE6062C84927917C05168C34FD17823BA5EF5C13F963D335054006E"


class LiveRiskService:
    """Evaluates live disruption risk using the existing PyTorch ST-GNN inference engine."""

    def __init__(
        self,
        storage: Optional[WeatherStorage] = None,
        checkpoint_path: Optional[Path | str] = None,
        static_path: Optional[Path | str] = None,
    ) -> None:
        self.storage = storage or weather_storage
        self.checkpoint_path = Path(checkpoint_path or settings.checkpoint_path)
        self.static_path = Path(static_path or settings.static_segments_path)
        self._engine: Optional[RiskInferenceEngine] = None
        self._static_df: Optional[pd.DataFrame] = None
        self._checkpoint_sha256 = self._compute_checkpoint_sha256()

    def _compute_checkpoint_sha256(self) -> str:
        if not self.checkpoint_path.is_file():
            return "CHECKPOINT_NOT_FOUND"
        hasher = hashlib.sha256()
        with open(self.checkpoint_path, "rb") as f:
            for chunk in iter(lambda: f.read(65536), b""):
                hasher.update(chunk)
        return hasher.hexdigest().upper()

    def _get_engine(self) -> RiskInferenceEngine:
        if self._engine is None:
            if not self.checkpoint_path.is_file():
                raise FileNotFoundError(f"Checkpoint not found at {self.checkpoint_path}")
            self._engine = RiskInferenceEngine(checkpoint_path=self.checkpoint_path)
        return self._engine

    def _get_static_df(self) -> pd.DataFrame:
        if self._static_df is None:
            if not self.static_path.is_file():
                raise FileNotFoundError(f"Static segments file not found at {self.static_path}")
            self._static_df = pd.read_csv(self.static_path)
        return self._static_df

    def _get_connection(self) -> sqlite3.Connection:
        self.storage.db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(self.storage.db_path))
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode = WAL;")
        conn.execute("PRAGMA synchronous = NORMAL;")
        return conn

    def init_db(self) -> None:
        """Initializes the live_risk table and indexes in the runtime database."""
        with self._get_connection() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS live_risk (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    segment_id TEXT NOT NULL,
                    as_of TEXT NOT NULL,
                    score REAL,
                    tier TEXT NOT NULL,
                    status TEXT NOT NULL,
                    is_stale INTEGER NOT NULL DEFAULT 0,
                    model_version TEXT NOT NULL,
                    checkpoint_sha256 TEXT NOT NULL,
                    weather_window_end TEXT NOT NULL,
                    computed_at TEXT NOT NULL,
                    UNIQUE(segment_id, as_of)
                );
                """
            )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_live_risk_as_of ON live_risk(as_of);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_live_risk_seg_as_of ON live_risk(segment_id, as_of);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_live_risk_computed ON live_risk(computed_at);")
            conn.commit()

    def prune_old_records(self, max_history_days: int = 7) -> int:
        """Enforces a bounded 7-day history limit in live_risk table."""
        self.init_db()
        cutoff_date = (datetime.now(timezone.utc) - timedelta(days=max_history_days)).strftime("%Y-%m-%d")
        with self._get_connection() as conn:
            cur = conn.execute("DELETE FROM live_risk WHERE as_of < ?", (cutoff_date,))
            deleted = cur.rowcount
            conn.commit()
        if deleted > 0:
            logger.info("Pruned %d expired live risk records older than %s", deleted, cutoff_date)
        return deleted

    def compute_live_risk(
        self,
        as_of: Optional[str] = None,
        eval_time: Optional[datetime] = None,
    ) -> List[Dict[str, Any]]:
        """Evaluates ST-GNN risk predictions from weather_observation and persists them."""
        self.init_db()
        engine = self._get_engine()
        static_df = self._get_static_df()

        # 1. Determine evaluation time and target date
        wall_clock = eval_time or datetime.now(timezone.utc)
        if as_of is None:
            # Prefer the latest available observation date in the runtime DB
            latest_db_date = self.storage.get_latest_observation_date()
            target_date = latest_db_date or wall_clock.strftime("%Y-%m-%d")
        else:
            target_date = as_of

        # 2. Extract 7-day lookback window from weather_observation
        # Prefer 'open-meteo' (or other live provider) unless in replay mode
        source_filter = "replay" if settings.live_mode == "replay" else None
        target_dt = pd.to_datetime(target_date)
        start_dt = target_dt - timedelta(days=6)
        start_date = start_dt.strftime("%Y-%m-%d")

        obs_df = self.storage.get_observations(
            start_date=start_date,
            end_date=target_date,
            source=source_filter,
        )

        # If source_filter was None but we have both live and replay, filter to live if available
        if source_filter is None and not obs_df.empty and "open-meteo" in obs_df["source"].values:
            obs_df = obs_df[obs_df["source"] == "open-meteo"].copy()

        # Map 'obs_date' to 'date' for the inference engine (must be present even when empty)
        if "date" not in obs_df.columns:
            obs_df["date"] = obs_df["obs_date"] if "obs_date" in obs_df.columns else []

        # 3. Call existing inference engine
        # In live mode, evaluate staleness against wall-clock time; in replay mode, evaluate against target date
        if eval_time is not None:
            effective_eval_time = eval_time
        elif settings.live_mode == "live":
            effective_eval_time = wall_clock
        else:
            effective_eval_time = target_dt + timedelta(hours=12)

        predictions: List[SegmentPrediction] = engine.predict_corridor(
            target_date=target_date,
            weather_df=obs_df,
            static_df=static_df,
            eval_time=effective_eval_time,
            stale_hours_limit=24.0,
        )

        # 4. Persist to live_risk table
        now_iso = datetime.now(timezone.utc).isoformat()
        records = []
        for p in predictions:
            records.append((
                p.segment_id,
                target_date,
                p.risk_score,
                p.risk_tier,
                p.status,
                1 if p.is_stale else 0,
                p.model_version,
                self._checkpoint_sha256,
                target_date,
                now_iso,
            ))

        sql = """
            INSERT INTO live_risk (
                segment_id, as_of, score, tier, status, is_stale,
                model_version, checkpoint_sha256, weather_window_end, computed_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(segment_id, as_of) DO UPDATE SET
                score = excluded.score,
                tier = excluded.tier,
                status = excluded.status,
                is_stale = excluded.is_stale,
                model_version = excluded.model_version,
                checkpoint_sha256 = excluded.checkpoint_sha256,
                weather_window_end = excluded.weather_window_end,
                computed_at = excluded.computed_at;
        """

        with self._get_connection() as conn:
            conn.executemany(sql, records)
            conn.commit()

        # Enforce bounded 7-day history
        self.prune_old_records()

        logger.info(
            "Computed and persisted live risk for %d segments (as_of: %s, status: %s)",
            len(predictions),
            target_date,
            predictions[0].status if predictions else "EMPTY",
        )

        out = []
        for p in predictions:
            d = p.to_dict()
            d["checkpoint_sha256"] = self._checkpoint_sha256
            d["weather_window_end"] = target_date
            out.append(d)
        return out

    def get_latest_live_risk(self) -> Dict[str, Any]:
        """Retrieves the latest live risk evaluation across all 151 segments."""
        self.init_db()
        with self._get_connection() as conn:
            latest_row = conn.execute("SELECT MAX(as_of) FROM live_risk").fetchone()
            latest_as_of = latest_row[0] if latest_row and latest_row[0] else None

            if not latest_as_of:
                # If no precomputed live risk, trigger initial computation
                self.compute_live_risk()
                latest_row = conn.execute("SELECT MAX(as_of) FROM live_risk").fetchone()
                latest_as_of = latest_row[0] if latest_row and latest_row[0] else None

            if not latest_as_of:
                return {
                    "as_of": None,
                    "computed_at": None,
                    "experimental": True,
                    "disclaimer": "Live data - Experimental - not validated. Relative advisory index.",
                    "model_version": self._get_engine().model_version,
                    "checkpoint_sha256": self._checkpoint_sha256,
                    "summary": {"Low": 0, "Medium": 0, "High": 0, "UNKNOWN": 151},
                    "segments": [],
                }

            rows = conn.execute(
                """
                SELECT segment_id, as_of, score, tier, status, is_stale,
                       model_version, checkpoint_sha256, weather_window_end, computed_at
                FROM live_risk
                WHERE as_of = ?
                ORDER BY segment_id ASC
                """,
                (latest_as_of,),
            ).fetchall()

        from src.services.hazard_event_service import hazard_event_service

        events_map = hazard_event_service.get_active_events_by_segment_map()
        segments = []
        summary = {"Low": 0, "Medium": 0, "High": 0, "UNKNOWN": 0}
        op_summary = {"OPEN": 0, "CAUTION": 0, "RESTRICTED": 0, "CLOSED": 0, "UNKNOWN": 0}
        computed_at = None

        for r in rows:
            tier = r["tier"]
            summary[tier] = summary.get(tier, 0) + 1
            computed_at = r["computed_at"]
            sid = r["segment_id"]
            seg_events = events_map.get(sid, [])
            op_status = hazard_event_service.derive_operational_status(
                model_risk_tier=tier,
                active_events=seg_events,
                model_status=r["status"],
            )
            op_summary[op_status] = op_summary.get(op_status, 0) + 1

            model_risk = {
                "risk_score": r["score"],
                "risk_tier": tier,
                "status": r["status"],
                "is_stale": bool(r["is_stale"]),
            }

            segments.append({
                "segment_id": sid,
                "risk_score": r["score"],
                "risk_tier": tier,
                "status": r["status"],
                "is_stale": bool(r["is_stale"]),
                "model_version": r["model_version"],
                "checkpoint_sha256": r["checkpoint_sha256"],
                "weather_window_end": r["weather_window_end"],
                "computed_at": r["computed_at"],
                "operational_status": op_status,
                "active_events": seg_events,
                "model_risk": model_risk,
            })

        return {
            "as_of": latest_as_of,
            "computed_at": computed_at,
            "experimental": True,
            "disclaimer": "Live data - Experimental - not validated. Relative advisory index.",
            "model_version": self._get_engine().model_version,
            "checkpoint_sha256": self._checkpoint_sha256,
            "summary": summary,
            "operational_summary": op_summary,
            "segments": segments,
        }

    def get_risk_changes(self, since: Optional[str] = None) -> Dict[str, Any]:
        """Returns risk records modified or computed since a given ISO timestamp."""
        self.init_db()
        with self._get_connection() as conn:
            if since:
                rows = conn.execute(
                    """
                    SELECT segment_id, as_of, score, tier, status, is_stale, computed_at
                    FROM live_risk
                    WHERE computed_at > ?
                    ORDER BY computed_at ASC
                    """,
                    (since,),
                ).fetchall()
            else:
                # Return latest evaluation if since is not provided
                latest_as_of_row = conn.execute("SELECT MAX(as_of) FROM live_risk").fetchone()
                latest_as_of = latest_as_of_row[0] if latest_as_of_row and latest_as_of_row[0] else None
                if latest_as_of:
                    rows = conn.execute(
                        """
                        SELECT segment_id, as_of, score, tier, status, is_stale, computed_at
                        FROM live_risk
                        WHERE as_of = ?
                        ORDER BY segment_id ASC
                        """,
                        (latest_as_of,),
                    ).fetchall()
                else:
                    rows = []

        changes = [
            {
                "segment_id": r["segment_id"],
                "as_of": r["as_of"],
                "risk_score": r["score"],
                "risk_tier": r["tier"],
                "status": r["status"],
                "is_stale": bool(r["is_stale"]),
                "computed_at": r["computed_at"],
            }
            for r in rows
        ]

        return {
            "since": since,
            "count": len(changes),
            "changes": changes,
        }

    def get_live_status(self) -> Dict[str, Any]:
        """Returns comprehensive operational status for live monitoring."""
        self.init_db()
        latest_weather_date = self.storage.get_latest_observation_date()
        latest_fetch = self.storage.get_latest_fetched_at()

        data_age_hours: Optional[float] = None
        if latest_fetch:
            try:
                fetch_dt = datetime.fromisoformat(latest_fetch.replace("Z", "+00:00"))
                data_age_hours = round((datetime.now(timezone.utc) - fetch_dt).total_seconds() / 3600.0, 2)
            except Exception:
                pass

        with self._get_connection() as conn:
            latest_as_of_row = conn.execute("SELECT MAX(as_of) FROM live_risk").fetchone()
            latest_as_of = latest_as_of_row[0] if latest_as_of_row and latest_as_of_row[0] else None

            if latest_as_of:
                unknown_count = conn.execute(
                    "SELECT COUNT(*) FROM live_risk WHERE as_of = ? AND tier = 'UNKNOWN'",
                    (latest_as_of,),
                ).fetchone()[0]
                stale_count = conn.execute(
                    "SELECT COUNT(*) FROM live_risk WHERE as_of = ? AND is_stale = 1",
                    (latest_as_of,),
                ).fetchone()[0]
                total_segments = conn.execute(
                    "SELECT COUNT(*) FROM live_risk WHERE as_of = ?",
                    (latest_as_of,),
                ).fetchone()[0]
            else:
                unknown_count = 151
                stale_count = 0
                total_segments = 0

        # Meteorological validation summary highlights
        validation_summary = {
            "evaluation_period": "2024-07-01 to 2024-07-31",
            "eval_segments": 151,
            "precip_mae_mm": 5.21,
            "precip_correlation": 0.61,
            "temp_mean_mae_c": 1.82,
            "distribution_shift_warning": "Open-Meteo exhibits lower convective peak rainfall than ERA5-Land in Pir Panjal mountain topography.",
        }

        return {
            "mode": settings.live_mode,
            "experimental": True,
            "provider": "open-meteo" if settings.live_mode == "live" else ("replay" if settings.live_mode == "replay" else "none"),
            "latest_fetch": latest_fetch,
            "data_age_hours": data_age_hours,
            "latest_weather_date": latest_weather_date,
            "latest_risk_as_of": latest_as_of,
            "total_segments": total_segments,
            "unknown_count": unknown_count,
            "stale_count": stale_count,
            "checkpoint_sha256": self._checkpoint_sha256,
            "validation_summary": validation_summary,
        }


live_risk_service = LiveRiskService()
