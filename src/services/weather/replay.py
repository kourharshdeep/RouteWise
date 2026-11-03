"""Replay Weather Provider for RouteWise.

Replays historical ERA5-Land reanalysis from data/weather_daily_by_segment.csv
(read-only) as if live, stamping every record with source="replay".
Enables deterministic local testing and scenario replays without external API dependencies.
"""
from __future__ import annotations

import csv
import logging
from datetime import date, datetime, timezone
from pathlib import Path
from typing import List, Optional, Sequence

import pandas as pd

from src.api.config import settings
from src.services.weather.base import EXPECTED_DYNAMIC_FEATURES, WeatherProvider

logger = logging.getLogger("replay_provider")


class ReplayProvider(WeatherProvider):
    """Weather provider that replays historical days from CSV as simulated live data."""

    def __init__(self, csv_path: Path | str | None = None) -> None:
        self.csv_path = Path(csv_path or settings.weather_daily_path)
        if not self.csv_path.is_file():
            raise FileNotFoundError(f"Replay weather CSV not found at {self.csv_path}")

    @property
    def provider_name(self) -> str:
        return "replay"

    def fetch(
        self,
        start_date: str | date,
        end_date: str | date | None = None,
        segments: Sequence[str] | None = None,
    ) -> pd.DataFrame:
        """Fetches weather records for a specified date range and optional segment filter.
        
        Args:
            start_date: Starting observation date (YYYY-MM-DD or date object).
            end_date: Optional end observation date. If None, defaults to start_date.
            segments: Optional list of segment_ids to filter by.
            
        Returns:
            pd.DataFrame matching WeatherProvider contract with source="replay".
        """
        start_str = start_date.isoformat() if isinstance(start_date, (date, datetime)) else str(start_date)
        end_str = end_date.isoformat() if isinstance(end_date, (date, datetime)) else (str(end_date) if end_date else start_str)

        segment_set = set(segments) if segments else None
        now_iso = datetime.now(timezone.utc).isoformat()

        matching_rows: List[dict] = []

        with open(self.csv_path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                r_date = row.get("date", "")
                if start_str <= r_date <= end_str:
                    seg_id = row.get("segment_id", "")
                    if segment_set and seg_id not in segment_set:
                        continue
                    
                    matching_rows.append({
                        "segment_id": seg_id,
                        "obs_date": r_date,
                        "precip_mm": float(row.get("precip_mm", 0.0) or 0.0),
                        "snowfall_mm_we": float(row.get("snowfall_mm_we", 0.0) or 0.0),
                        "temp_mean_c": float(row.get("temp_mean_c", 0.0) or 0.0),
                        "temp_min_c": float(row.get("temp_min_c", 0.0) or 0.0),
                        "snow_depth_m": float(row.get("snow_depth_m", 0.0) or 0.0),
                        "precip_3d_mm": float(row.get("precip_3d_mm", 0.0) or 0.0),
                        "precip_7d_mm": float(row.get("precip_7d_mm", 0.0) or 0.0),
                        "source": "replay",
                        "fetched_at": now_iso,
                        "quality_flag": "OK",
                    })

        columns = ["segment_id", "obs_date"] + EXPECTED_DYNAMIC_FEATURES + ["source", "fetched_at", "quality_flag"]
        if not matching_rows:
            return pd.DataFrame(columns=columns)

        df = pd.DataFrame(matching_rows, columns=columns)
        return df
