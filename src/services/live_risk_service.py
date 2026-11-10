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

import contextlib
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

# Authoritative data freshness threshold across RouteWise (24 hours)
MAX_DATA_AGE_HOURS: float = 24.0


class LiveRiskComputationDisabledError(RuntimeError):
    """Raised when live-risk computation is disabled by configuration (e.g. ROUTEWISE_LIVE_MODE is 'off')."""
    pass


class LiveRiskService:
    """Evaluates live disruption risk using the existing PyTorch ST-GNN inference engine."""

    # Missing-data threshold matching src/models/inference.py (0.25 = 25%)
    MISSING_DATA_THRESHOLD: float = 0.25
    MAX_DATA_AGE_HOURS: float = MAX_DATA_AGE_HOURS

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
        self._initialized_dbs: set[Path] = set()
        self._risk_rows_cache: Optional[Dict[str, Any]] = None

    def invalidate_cache(self) -> None:
        """Invalidates in-memory risk cache when records are updated."""
        self._risk_rows_cache = None

    def reset_db_init(self) -> None:
        """Clears DB initialization tracking for tests."""
        self._initialized_dbs.clear()
        self._risk_rows_cache = None

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
        db_path = self.storage.db_path
        if db_path in self._initialized_dbs and db_path.is_file():
            try:
                with contextlib.closing(sqlite3.connect(str(db_path))) as conn:
                    if conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='live_risk'").fetchone():
                        return
            except Exception:
                pass
            self._initialized_dbs.discard(db_path)

        with contextlib.closing(self._get_connection()) as conn:
            with conn:
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
                        source TEXT NOT NULL DEFAULT 'open-meteo',
                        UNIQUE(segment_id, as_of)
                    );
                    """
                )
                conn.execute("CREATE INDEX IF NOT EXISTS idx_live_risk_as_of ON live_risk(as_of);")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_live_risk_seg_as_of ON live_risk(segment_id, as_of);")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_live_risk_as_of_seg ON live_risk(as_of, segment_id);")
                conn.execute("CREATE INDEX IF NOT EXISTS idx_live_risk_computed ON live_risk(computed_at);")

                # Additive idempotent migration for legacy databases lacking weather_window_end or source
                columns = [row[1] for row in conn.execute("PRAGMA table_info(live_risk);").fetchall()]
                if "weather_window_end" not in columns:
                    conn.execute("ALTER TABLE live_risk ADD COLUMN weather_window_end TEXT;")
                if "source" not in columns:
                    conn.execute("ALTER TABLE live_risk ADD COLUMN source TEXT NOT NULL DEFAULT 'open-meteo';")

                conn.execute("CREATE INDEX IF NOT EXISTS idx_live_risk_source_as_of ON live_risk(source, as_of);")
        self._initialized_dbs.add(db_path)

    def prune_old_records(self, max_history_days: int = 7, eval_time: Optional[datetime] = None) -> int:
        """Enforces a bounded 7-day history limit in live_risk table."""
        self.init_db()
        ref_time = eval_time or datetime.now(timezone.utc)
        cutoff_date = (ref_time - timedelta(days=max_history_days)).strftime("%Y-%m-%d")
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
        source: Optional[str] = None,
        weather_window_end: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Evaluates ST-GNN risk predictions from weather_observation and persists them."""
        self.init_db()
        engine = self._get_engine()
        static_df = self._get_static_df()

        # 1. Determine source filter first
        # Prefer specified source, else 'replay' if replay mode, 'open-meteo' if live mode
        if source is not None:
            source_filter = source
        elif settings.live_mode == "replay":
            source_filter = "replay"
        elif settings.live_mode == "live":
            source_filter = "open-meteo"
        else:
            raise LiveRiskComputationDisabledError(
                "Live-risk computation is disabled by configuration (ROUTEWISE_LIVE_MODE is 'off')."
            )

        # 2. Determine evaluation time (UTC), advisory target date (as_of), and weather lookback window end
        raw_clock = eval_time or datetime.now(timezone.utc)
        if raw_clock.tzinfo is None:
            wall_clock = raw_clock.replace(tzinfo=timezone.utc)
        else:
            wall_clock = raw_clock.astimezone(timezone.utc)
        today_utc = wall_clock.date()
        yesterday_utc = today_utc - timedelta(days=1)

        if weather_window_end is not None:
            win_end = weather_window_end
            target_as_of = as_of or (pd.to_datetime(win_end) + timedelta(days=1)).strftime("%Y-%m-%d")
        elif as_of is not None:
            target_as_of = as_of
            win_end = as_of
        else:
            if source_filter == "open-meteo" or settings.live_mode == "live":
                target_as_of = today_utc.strftime("%Y-%m-%d")
                # In live mode: today's ongoing UTC observations are incomplete. Lookback window ends on yesterday UTC
                win_end = yesterday_utc.strftime("%Y-%m-%d")
            else:
                # In replay mode: use latest available date in DB for the replay source
                latest_db_date = self.storage.get_latest_observation_date(source=source_filter)
                if not latest_db_date:
                    logger.warning("Replay mode active but no replay observations found in database.")
                    return [
                        {
                            "segment_id": seg,
                            "as_of": None,
                            "risk_score": None,
                            "risk_tier": "UNKNOWN",
                            "status": "NO_DATA",
                            "is_stale": False,
                            "model_version": engine.model_version,
                            "checkpoint_sha256": self._checkpoint_sha256,
                            "weather_window_end": None,
                            "prediction_horizon_hours": 24,
                            "data_timestamp": None,
                            "warning": "No replay weather observations found.",
                        }
                        for seg in engine.segment_order
                    ]
                target_as_of = latest_db_date
                win_end = target_as_of

        # 3. Extract 7-day lookback window from weather_observation [win_end - 6 days, win_end]
        target_dt = pd.to_datetime(win_end)
        start_dt = target_dt - timedelta(days=6)
        start_date = start_dt.strftime("%Y-%m-%d")

        obs_df = self.storage.get_observations(
            start_date=start_date,
            end_date=win_end,
            source=source_filter,
        )

        # If source_filter was None but we have both live and replay, filter to live if available
        if source_filter is None and not obs_df.empty and "open-meteo" in obs_df["source"].values:
            obs_df = obs_df[obs_df["source"] == "open-meteo"].copy()

        # Map 'obs_date' to 'date' for the inference engine (must be present even when empty)
        if "date" not in obs_df.columns:
            obs_df["date"] = obs_df["obs_date"] if "obs_date" in obs_df.columns else []

        now_iso = datetime.now(timezone.utc).isoformat()

        # 3. Detect segments with missing, incomplete, or flagged observations in 7-day lookback window
        missing_segment_ids = set()
        required_dates = set(pd.date_range(start=start_date, end=win_end, freq="D").strftime("%Y-%m-%d"))

        if obs_df.empty:
            missing_segment_ids = set(engine.segment_order)
        else:
            for seg in engine.segment_order:
                seg_sub = obs_df[obs_df["segment_id"] == seg]
                seg_dates = set(seg_sub["obs_date"].dropna().unique())
                if not required_dates.issubset(seg_dates):
                    missing_segment_ids.add(seg)
                    continue

                has_missing_feature = False
                for _, row in seg_sub.iterrows():
                    q_flag = str(row.get("quality_flag", "OK"))
                    if q_flag in ("MISSING_DATA", "PARTIAL_WINDOW"):
                        has_missing_feature = True
                        break
                    for feat in EXPECTED_DYNAMIC_FEATURES:
                        val = row.get(feat)
                        if val is None or pd.isna(val):
                            has_missing_feature = True
                            break
                    if has_missing_feature:
                        break

                if has_missing_feature:
                    missing_segment_ids.add(seg)

        # In live mode, evaluate staleness against wall-clock time; in replay mode, evaluate against target date
        if eval_time is not None:
            effective_eval_time = eval_time
        elif settings.live_mode == "live":
            effective_eval_time = wall_clock
        else:
            effective_eval_time = target_dt + timedelta(hours=12)

        n_total_segs = len(engine.segment_order)
        missing_fraction = len(missing_segment_ids) / n_total_segs if n_total_segs > 0 else 1.0

        if missing_fraction > self.MISSING_DATA_THRESHOLD:
            # Missing data exceeds threshold (25%): all corridor segments are flagged MISSING_DATA/UNKNOWN
            predictions: List[SegmentPrediction] = [
                SegmentPrediction(
                    segment_id=seg,
                    risk_score=None,
                    risk_tier="UNKNOWN",
                    status="MISSING_DATA",
                    is_stale=False,
                    model_version=engine.model_version,
                    prediction_horizon_hours=24,
                    data_timestamp=f"{target_as_of}T00:00:00Z",
                    warning=f"Corridor missing weather observations ({missing_fraction * 100:.1f}%) exceed threshold ({self.MISSING_DATA_THRESHOLD * 100:.0f}%).",
                )
                for seg in engine.segment_order
            ]
        else:
            # Find segments adjacent to missing segments (via adjacency matrix A_hat)
            neighbor_segment_ids = set()
            for m_seg in missing_segment_ids:
                m_idx = engine.seg_to_idx.get(m_seg)
                if m_idx is not None:
                    row_adj = engine.A_hat[m_idx]
                    for j, val in enumerate(row_adj):
                        if j != m_idx and val > 0:
                            n_seg = engine.segment_order[j]
                            if n_seg not in missing_segment_ids:
                                neighbor_segment_ids.add(n_seg)

            # Prepare sanitized_df so no unfilled/NaN values can ever reach the model tensor
            sanitized_df = obs_df.copy()
            clean_sub = sanitized_df[~sanitized_df["segment_id"].isin(missing_segment_ids)]

            daily_means: Dict[str, Dict[str, float]] = {}
            for d in required_dates:
                d_rows = clean_sub[clean_sub["obs_date"] == d]
                daily_means[d] = {}
                for feat in EXPECTED_DYNAMIC_FEATURES:
                    if not d_rows.empty and not pd.isna(d_rows[feat].mean()):
                        daily_means[d][feat] = float(d_rows[feat].mean())
                    else:
                        daily_means[d][feat] = 0.0

            filled_records = []
            for seg in missing_segment_ids:
                for d in required_dates:
                    rec = {
                        "segment_id": seg,
                        "obs_date": d,
                        "date": d,
                        "source": source_filter or "open-meteo",
                        "fetched_at": now_iso,
                        "quality_flag": "OK",
                    }
                    for feat in EXPECTED_DYNAMIC_FEATURES:
                        rec[feat] = daily_means[d][feat]
                    filled_records.append(rec)

            if filled_records:
                sanitized_df = sanitized_df[~sanitized_df["segment_id"].isin(missing_segment_ids)]
                sanitized_df = pd.concat([sanitized_df, pd.DataFrame(filled_records)], ignore_index=True)

            if "date" not in sanitized_df.columns:
                sanitized_df["date"] = sanitized_df["obs_date"]

            raw_predictions = engine.predict_corridor(
                target_date=win_end,
                weather_df=sanitized_df,
                static_df=static_df,
                eval_time=None,
            )

            # Authoritative staleness evaluation: fresh if weather_window_end is yesterday (UTC) relative to clock
            is_stale_compute = False
            win_d = pd.to_datetime(win_end).date()
            if source_filter == "replay" or settings.live_mode == "replay":
                if eval_time is not None:
                    eval_d = (eval_time.astimezone(timezone.utc) if eval_time.tzinfo else eval_time.replace(tzinfo=timezone.utc)).date()
                    if (eval_d - win_d).days > 1:
                        is_stale_compute = True
            else:
                if win_d < yesterday_utc:
                    is_stale_compute = True

            # Map predictions: missing segments -> MISSING_DATA; adjacent neighbors -> NEIGHBOUR_DATA_MISSING; stale -> STALE_DATA
            predictions: List[SegmentPrediction] = []
            for p in raw_predictions:
                if is_stale_compute:
                    predictions.append(
                        SegmentPrediction(
                            segment_id=p.segment_id,
                            risk_score=p.risk_score,
                            risk_tier="UNKNOWN",
                            status="STALE_DATA",
                            is_stale=True,
                            model_version=p.model_version,
                            prediction_horizon_hours=p.prediction_horizon_hours,
                            data_timestamp=p.data_timestamp,
                            warning="Weather observation lookback window is older than operational freshness limit.",
                        )
                    )
                elif p.segment_id in missing_segment_ids:
                    predictions.append(
                        SegmentPrediction(
                            segment_id=p.segment_id,
                            risk_score=None,
                            risk_tier="UNKNOWN",
                            status="MISSING_DATA",
                            is_stale=False,
                            model_version=p.model_version,
                            prediction_horizon_hours=p.prediction_horizon_hours,
                            data_timestamp=p.data_timestamp,
                            warning="Weather observation data missing or incomplete for segment lookback window.",
                        )
                    )
                elif p.segment_id in neighbor_segment_ids:
                    predictions.append(
                        SegmentPrediction(
                            segment_id=p.segment_id,
                            risk_score=None,
                            risk_tier="UNKNOWN",
                            status="NEIGHBOUR_DATA_MISSING",
                            is_stale=False,
                            model_version=p.model_version,
                            prediction_horizon_hours=p.prediction_horizon_hours,
                            data_timestamp=p.data_timestamp,
                            warning="Adjacent road segment has missing weather observations; spatial convolution relies on imputed data.",
                        )
                    )
                else:
                    predictions.append(p)

        # 4. Persist to live_risk table
        records = []
        for p in predictions:
            records.append((
                p.segment_id,
                target_as_of,
                p.risk_score,
                p.risk_tier,
                p.status,
                1 if p.is_stale else 0,
                p.model_version,
                self._checkpoint_sha256,
                win_end,
                now_iso,
                source_filter or "open-meteo",
            ))

        sql = """
            INSERT INTO live_risk (
                segment_id, as_of, score, tier, status, is_stale,
                model_version, checkpoint_sha256, weather_window_end, computed_at, source
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(segment_id, as_of) DO UPDATE SET
                score = excluded.score,
                tier = excluded.tier,
                status = excluded.status,
                is_stale = excluded.is_stale,
                model_version = excluded.model_version,
                checkpoint_sha256 = excluded.checkpoint_sha256,
                weather_window_end = excluded.weather_window_end,
                computed_at = excluded.computed_at,
                source = excluded.source;
        """

        with self._get_connection() as conn:
            conn.executemany(sql, records)
            conn.commit()

        self.invalidate_cache()

        # Enforce bounded 7-day history
        self.prune_old_records(eval_time=effective_eval_time)

        logger.info(
            "Computed and persisted live risk for %d segments (as_of: %s, weather_window_end: %s, status: %s)",
            len(predictions),
            target_as_of,
            win_end,
            predictions[0].status if predictions else "EMPTY",
        )

        # Broadcast real-time SSE updates if broadcaster is active
        try:
            from src.services.live_broadcast_service import live_broadcaster
            live_broadcaster.broadcast_sync("risk_update", {
                "as_of": target_as_of,
                "weather_window_end": win_end,
                "computed_at": now_iso,
                "segments_count": len(records),
            })
            live_broadcaster.broadcast_sync("route_update", {
                "reason": "risk_recomputed",
                "as_of": target_as_of,
                "timestamp": now_iso,
            })
            live_broadcaster.broadcast_sync("status", self.get_live_status())
        except Exception as e:
            logger.warning("Live risk broadcast failed: %s", e, exc_info=True)

        out = []
        for p in predictions:
            d = p.to_dict()
            d["as_of"] = target_as_of
            d["checkpoint_sha256"] = self._checkpoint_sha256
            d["weather_window_end"] = win_end
            out.append(d)
        return out

    def get_latest_live_risk(self, as_of: Optional[str] = None, eval_time: Optional[datetime] = None) -> Dict[str, Any]:
        """Retrieves the live risk evaluation across all 151 segments (latest or for a specified date)."""
        self.init_db()
        with self._get_connection() as conn:
            if as_of:
                target_as_of = as_of
            else:
                if settings.live_mode == "replay":
                    latest_row = conn.execute(
                        "SELECT MAX(as_of) FROM live_risk WHERE source = 'replay'"
                    ).fetchone()
                elif settings.live_mode == "live":
                    latest_row = conn.execute(
                        "SELECT MAX(as_of) FROM live_risk WHERE (source = 'open-meteo' OR source IS NULL)"
                    ).fetchone()
                else:
                    latest_row = conn.execute("SELECT MAX(as_of) FROM live_risk").fetchone()
                target_as_of = latest_row[0] if latest_row and latest_row[0] else None

            if not target_as_of:
                fallback_ver = (
                    self._engine.model_version
                    if self._engine
                    else (
                        self._checkpoint_sha256[:16]
                        if self._checkpoint_sha256 != "CHECKPOINT_NOT_FOUND"
                        else "UNKNOWN"
                    )
                )
                return {
                    "as_of": None,
                    "weather_window_end": None,
                    "computed_at": None,
                    "experimental": True,
                    "disclaimer": "Live data - Experimental - not validated. Relative advisory index.",
                    "model_version": fallback_ver,
                    "checkpoint_sha256": self._checkpoint_sha256,
                    "summary": {"Low": 0, "Medium": 0, "High": 0, "UNKNOWN": 151},
                    "operational_summary": {"OPEN": 0, "CAUTION": 0, "RESTRICTED": 0, "CLOSED": 0, "UNKNOWN": 151},
                    "segments": [],
                }

            cache_key = (str(self.storage.db_path), target_as_of, settings.live_mode, as_of)
            if self._risk_rows_cache and self._risk_rows_cache.get("key") == cache_key:
                rows = self._risk_rows_cache["rows"]
            else:
                if as_of:
                    rows = conn.execute(
                        """
                        SELECT segment_id, as_of, score, tier, status, is_stale,
                               model_version, checkpoint_sha256, weather_window_end, computed_at
                        FROM live_risk
                        WHERE as_of = ?
                        ORDER BY segment_id ASC
                        """,
                        (target_as_of,),
                    ).fetchall()
                elif settings.live_mode == "replay":
                    rows = conn.execute(
                        """
                        SELECT segment_id, as_of, score, tier, status, is_stale,
                               model_version, checkpoint_sha256, weather_window_end, computed_at
                        FROM live_risk
                        WHERE as_of = ? AND source = 'replay'
                        ORDER BY segment_id ASC
                        """,
                        (target_as_of,),
                    ).fetchall()
                elif settings.live_mode == "live":
                    rows = conn.execute(
                        """
                        SELECT segment_id, as_of, score, tier, status, is_stale,
                               model_version, checkpoint_sha256, weather_window_end, computed_at
                        FROM live_risk
                        WHERE as_of = ? AND (source = 'open-meteo' OR source IS NULL)
                        ORDER BY segment_id ASC
                        """,
                        (target_as_of,),
                    ).fetchall()
                else:
                    rows = conn.execute(
                        """
                        SELECT segment_id, as_of, score, tier, status, is_stale,
                               model_version, checkpoint_sha256, weather_window_end, computed_at
                        FROM live_risk
                        WHERE as_of = ?
                        ORDER BY segment_id ASC
                        """,
                        (target_as_of,),
                    ).fetchall()
                self._risk_rows_cache = {"key": cache_key, "rows": rows}

        from src.services.hazard_event_service import hazard_event_service

        raw_now = eval_time or datetime.now(timezone.utc)
        if raw_now.tzinfo is None:
            effective_now = raw_now.replace(tzinfo=timezone.utc)
        else:
            effective_now = raw_now.astimezone(timezone.utc)
        now_today_utc = effective_now.date()
        now_yesterday_utc = now_today_utc - timedelta(days=1)

        inc_sim = (getattr(settings, "live_mode", "live") == "replay")
        events_map = hazard_event_service.get_active_events_by_segment_map(
            now=effective_now,
            include_simulated=inc_sim,
        )
        segments = []
        summary = {"Low": 0, "Medium": 0, "High": 0, "UNKNOWN": 0}
        op_summary = {"OPEN": 0, "CAUTION": 0, "RESTRICTED": 0, "CLOSED": 0, "UNKNOWN": 0}
        computed_at = None

        for r in rows:
            sid = r["segment_id"]
            computed_at = r["computed_at"]
            db_is_stale = bool(r["is_stale"])

            # Read-time authoritative staleness evaluation relative to effective_now
            is_stale_read = db_is_stale

            # 1. Evaluate computed_at age against MAX_DATA_AGE_HOURS (24.0h)
            if not is_stale_read:
                if not computed_at:
                    is_stale_read = True
                else:
                    try:
                        comp_dt = datetime.fromisoformat(computed_at.replace("Z", "+00:00"))
                        if (effective_now - comp_dt).total_seconds() > MAX_DATA_AGE_HOURS * 3600:
                            is_stale_read = True
                    except Exception:
                        is_stale_read = True

            # 2. Evaluate weather window end
            if not is_stale_read:
                if not r["weather_window_end"]:
                    is_stale_read = True
                else:
                    try:
                        win_d = datetime.strptime(r["weather_window_end"][:10], "%Y-%m-%d").date()
                        if settings.live_mode == "replay":
                            target_d = datetime.strptime(target_as_of[:10], "%Y-%m-%d").date()
                            if (target_d - win_d).days > 1:
                                is_stale_read = True
                        else:
                            if win_d < now_yesterday_utc:
                                is_stale_read = True
                    except Exception:
                        is_stale_read = True

            status = "STALE_DATA" if is_stale_read and r["status"] == "OK" else r["status"]
            tier = "UNKNOWN" if is_stale_read else r["tier"]
            score = None if is_stale_read else r["score"]

            summary[tier] = summary.get(tier, 0) + 1
            seg_events = events_map.get(sid, [])
            op_status = hazard_event_service.derive_operational_status(
                model_risk_tier=tier,
                active_events=seg_events,
                model_status=status,
            )
            op_summary[op_status] = op_summary.get(op_status, 0) + 1

            model_risk = {
                "risk_score": score,
                "risk_tier": tier,
                "status": status,
                "is_stale": is_stale_read,
            }

            segments.append({
                "segment_id": sid,
                "risk_score": score,
                "risk_tier": tier,
                "status": status,
                "is_stale": is_stale_read,
                "model_version": r["model_version"],
                "checkpoint_sha256": r["checkpoint_sha256"],
                "weather_window_end": r["weather_window_end"],
                "computed_at": r["computed_at"],
                "operational_status": op_status,
                "active_events": seg_events,
                "model_risk": model_risk,
            })

        model_version = (
            rows[0]["model_version"]
            if rows
            else (
                self._engine.model_version
                if self._engine
                else (
                    self._checkpoint_sha256[:16]
                    if self._checkpoint_sha256 != "CHECKPOINT_NOT_FOUND"
                    else "UNKNOWN"
                )
            )
        )

        top_window_end = rows[0]["weather_window_end"] if rows else None

        return {
            "as_of": target_as_of,
            "weather_window_end": top_window_end,
            "computed_at": computed_at,
            "experimental": True,
            "disclaimer": "Live data - Experimental - not validated. Relative advisory index.",
            "model_version": model_version,
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
        provider_source = "open-meteo" if settings.live_mode == "live" else ("replay" if settings.live_mode == "replay" else None)
        latest_weather_date = self.storage.get_latest_observation_date(source=provider_source)
        latest_fetch = self.storage.get_latest_fetched_at(source=provider_source)

        data_age_hours: Optional[float] = None
        if settings.live_mode == "replay":
            data_age_hours = 0.0
        elif latest_fetch:
            try:
                fetch_dt = datetime.fromisoformat(latest_fetch.replace("Z", "+00:00"))
                data_age_hours = round((datetime.now(timezone.utc) - fetch_dt).total_seconds() / 3600.0, 2)
            except Exception:
                pass

        with self._get_connection() as conn:
            if settings.live_mode == "replay":
                latest_as_of_row = conn.execute(
                    "SELECT MAX(as_of) FROM live_risk WHERE source = 'replay'",
                ).fetchone()
            elif settings.live_mode == "live":
                latest_as_of_row = conn.execute(
                    "SELECT MAX(as_of) FROM live_risk WHERE (source = 'open-meteo' OR source IS NULL)"
                ).fetchone()
            else:
                latest_as_of_row = conn.execute("SELECT MAX(as_of) FROM live_risk").fetchone()
            latest_as_of = latest_as_of_row[0] if latest_as_of_row and latest_as_of_row[0] else None

            if latest_as_of:
                where_clause = "WHERE as_of = ?"
                params = [latest_as_of]
                if settings.live_mode == "replay":
                    where_clause += " AND source = 'replay'"
                elif settings.live_mode == "live":
                    where_clause += " AND (source = 'open-meteo' OR source IS NULL)"

                unknown_count = conn.execute(
                    f"SELECT COUNT(*) FROM live_risk {where_clause} AND tier = 'UNKNOWN'",
                    params,
                ).fetchone()[0]
                stale_count = conn.execute(
                    f"SELECT COUNT(*) FROM live_risk {where_clause} AND is_stale = 1",
                    params,
                ).fetchone()[0]
                total_segments = conn.execute(
                    f"SELECT COUNT(*) FROM live_risk {where_clause}",
                    params,
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
