"""Open-Meteo Weather Provider for Live Atmospheric Ingestion.

Honest Framing:
The RouteWise ST-GNN model was trained on ERA5-Land atmospheric reanalysis.
Live weather fetched from Open-Meteo represents a distribution shift.
All predictions derived from this provider must be treated as experimental.

Assumptions:
1. Snowfall conversion: Open-Meteo returns daily snowfall in centimeters (cm).
   ERA5-Land expects millimeters of water equivalent (mm_we).
   We apply the standard hydrological 10:1 snow-to-water ratio:
   1 cm fresh snow = 1.0 mm water equivalent (assuming snow density ~100 kg/m³).
2. Snow depth: Open-Meteo hourly snow_depth (meters) is aggregated to daily maximum
   matching week2b_process_weather.py methodology.
3. Grid clustering: NH-44 segments are clustered into ~9km grid cells (matching
   ERA5-Land native resolution) so each cluster is fetched once and fanned out.
"""
from __future__ import annotations

import json
import logging
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta, timezone
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

import pandas as pd

from src.services.weather.base import EXPECTED_DYNAMIC_FEATURES, WeatherProvider
from src.services.weather.clustering import GridCluster, build_corridor_grid_clusters
from src.services.weather.rolling import compute_rolling_precipitation

logger = logging.getLogger("open_meteo_provider")

OPEN_METEO_FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
OPEN_METEO_ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"


class OpenMeteoProvider(WeatherProvider):
    """Fetches real-time and historical weather from Open-Meteo with cluster fan-out."""

    def __init__(
        self,
        base_url: str = OPEN_METEO_FORECAST_URL,
        timeout_seconds: float = 10.0,
        max_retries: int = 3,
        backoff_factor: float = 0.5,
        fetcher: Optional[Callable[[str, float], dict]] = None,
        storage: Optional[Any] = None,
        sleep_fn: Optional[Callable[[float], None]] = None,
    ) -> None:
        self.base_url = base_url
        self.timeout_seconds = timeout_seconds
        self.max_retries = max_retries
        self.backoff_factor = backoff_factor
        self._fetcher = fetcher or self._default_http_get
        self.storage = storage
        self.sleep_fn = sleep_fn or time.sleep
        self._clusters: Optional[List[GridCluster]] = None

    @property
    def provider_name(self) -> str:
        return "open-meteo"

    def get_clusters(self) -> List[GridCluster]:
        """Lazy-loads and caches corridor grid clusters (~9 km resolution)."""
        if self._clusters is None:
            self._clusters = build_corridor_grid_clusters()
        return self._clusters

    @staticmethod
    def _default_http_get(url: str, timeout: float) -> dict:
        """Zero-dependency HTTP GET with standard library."""
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "RouteWise-Atmospheric-Service/1.0"},
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = resp.read().decode("utf-8")
            return json.loads(data)

    def _request_with_retry(self, url: str) -> Optional[dict]:
        """Executes HTTP request with exponential backoff and rate-limit handling."""
        attempt = 0
        while attempt < self.max_retries:
            try:
                return self._fetcher(url, self.timeout_seconds)
            except urllib.error.HTTPError as he:
                attempt += 1
                logger.warning("HTTP %d fetching %s (attempt %d/%d): %s", he.code, url, attempt, self.max_retries, he.reason)
                if attempt >= self.max_retries:
                    break
                if he.code == 429:
                    # Rate limit encountered: back off more aggressively
                    sleep_time = (self.backoff_factor * (2 ** attempt)) + 1.0
                elif he.code in (500, 502, 503, 504):
                    sleep_time = self.backoff_factor * (2 ** attempt)
                else:
                    # Client errors (4xx other than 429) should not retry
                    logger.error("Non-retryable client error %d from Open-Meteo: %s", he.code, he.reason)
                    return None
                self.sleep_fn(sleep_time)
            except (urllib.error.URLError, TimeoutError, OSError) as ex:
                attempt += 1
                logger.warning("Network error fetching %s (attempt %d/%d): %s", url, attempt, self.max_retries, ex)
                if attempt >= self.max_retries:
                    break
                self.sleep_fn(self.backoff_factor * (2 ** attempt))
            except Exception as exc:
                logger.error("Unexpected error fetching Open-Meteo data: %s", exc, exc_info=True)
                return None

        logger.error("Exceeded max retries (%d) fetching weather from %s", self.max_retries, url)
        return None

    def fetch_cluster_raw(
        self,
        lat: float,
        lon: float,
        start_date: str,
        end_date: str,
    ) -> Optional[dict]:
        """Queries Open-Meteo for a specific (lat, lon) cluster point."""
        params = {
            "latitude": str(lat),
            "longitude": str(lon),
            "start_date": start_date,
            "end_date": end_date,
            "daily": "temperature_2m_mean,temperature_2m_min,precipitation_sum,snowfall_sum",
            "hourly": "snow_depth",
            "timezone": "UTC",
        }
        query_string = urllib.parse.urlencode(params)
        url = f"{self.base_url}?{query_string}"
        return self._request_with_retry(url)

    def parse_cluster_response(
        self,
        raw_json: dict,
        cluster: GridCluster,
    ) -> pd.DataFrame:
        """Parses Open-Meteo response into ERA5-Land aligned segment daily rows."""
        daily = raw_json.get("daily", {})
        times = daily.get("time", [])
        if not times:
            return pd.DataFrame()

        precip_sums = daily.get("precipitation_sum", [])
        snowfall_sums = daily.get("snowfall_sum", [])
        temp_means = daily.get("temperature_2m_mean", [])
        temp_mins = daily.get("temperature_2m_min", [])

        # Process hourly snow_depth into daily maximum (in meters)
        hourly = raw_json.get("hourly", {})
        hourly_times = hourly.get("time", [])
        hourly_depths = hourly.get("snow_depth", [])

        daily_snow_depth_map: Dict[str, float] = {}
        hourly_values_by_day: Dict[str, List[Optional[float]]] = {}

        for idx, t_str in enumerate(hourly_times):
            d_str = t_str[:10]
            raw_depth = hourly_depths[idx] if idx < len(hourly_depths) else None

            try:
                depth_val = float(raw_depth)
                if pd.isna(depth_val):
                    depth_val = None
            except (TypeError, ValueError):
                depth_val = None

            hourly_values_by_day.setdefault(d_str, []).append(depth_val)

        for d_str, values in hourly_values_by_day.items():
            if len(values) != 24 or any(value is None for value in values):
                daily_snow_depth_map[d_str] = float("nan")
            else:
                daily_snow_depth_map[d_str] = max(values)

        now_iso = datetime.now(timezone.utc).isoformat()
        rows: List[dict] = []

        for idx, obs_date in enumerate(times):
            # Units conversion & Hydrological Assumptions:
            # Preserve None as NaN (do NOT silently replace missing weather with 0.0)
            precip_raw = precip_sums[idx] if idx < len(precip_sums) else None
            precip_mm = float(precip_raw) if (precip_raw is not None and not pd.isna(precip_raw)) else float("nan")

            # ASSUMPTION: 10:1 Snow Water Equivalent ratio. 1 cm snow depth = 1 mm water equivalent.
            snowfall_raw = snowfall_sums[idx] if idx < len(snowfall_sums) else None
            snowfall_cm = float(snowfall_raw) if (snowfall_raw is not None and not pd.isna(snowfall_raw)) else float("nan")
            snowfall_mm_we = round(snowfall_cm * 1.0, 4) if not pd.isna(snowfall_cm) else float("nan")

            temp_mean_raw = temp_means[idx] if idx < len(temp_means) else None
            temp_mean_c = float(temp_mean_raw) if (temp_mean_raw is not None and not pd.isna(temp_mean_raw)) else float("nan")

            temp_min_raw = temp_mins[idx] if idx < len(temp_mins) else None
            temp_min_c = float(temp_min_raw) if (temp_min_raw is not None and not pd.isna(temp_min_raw)) else float("nan")

            snow_depth_m = daily_snow_depth_map.get(obs_date, float("nan"))

            # Check if any required feature is missing
            has_missing = any(
                pd.isna(v) for v in (precip_mm, snowfall_mm_we, temp_mean_c, temp_min_c, snow_depth_m)
            )
            quality_flag = "MISSING_DATA" if has_missing else "EXPERIMENTAL_LIVE"

            # Fan out cluster observations to all segments assigned to this cluster
            for seg_id in cluster.segment_ids:
                rows.append({
                    "segment_id": seg_id,
                    "obs_date": obs_date,
                    "precip_mm": precip_mm,
                    "snowfall_mm_we": snowfall_mm_we,
                    "temp_mean_c": temp_mean_c,
                    "temp_min_c": temp_min_c,
                    "snow_depth_m": snow_depth_m,
                    "precip_3d_mm": 0.0,  # Computed subsequently via rolling logic
                    "precip_7d_mm": 0.0,
                    "source": "open-meteo",
                    "fetched_at": now_iso,
                    "quality_flag": quality_flag,
                })

        return pd.DataFrame(rows)

    def fetch(
        self,
        start_date: str | date,
        end_date: str | date | None = None,
        segments: Sequence[str] | None = None,
    ) -> pd.DataFrame:
        """Fetches live weather from Open-Meteo fanning out over corridor clusters."""
        start_str = start_date.isoformat() if isinstance(start_date, (date, datetime)) else str(start_date)
        end_str = end_date.isoformat() if isinstance(end_date, (date, datetime)) else (str(end_date) if end_date else start_str)

        clusters = self.get_clusters()
        segment_filter = set(segments) if segments else None

        cluster_dfs: List[pd.DataFrame] = []

        for cluster in clusters:
            # If segment filter provided and no cluster segments match, skip fetching this cluster
            if segment_filter and not any(sid in segment_filter for sid in cluster.segment_ids):
                continue

            try:
                raw = self.fetch_cluster_raw(
                    lat=cluster.latitude,
                    lon=cluster.longitude,
                    start_date=start_str,
                    end_date=end_str,
                )
                if raw is not None:
                    parsed = self.parse_cluster_response(raw, cluster)
                    if not parsed.empty:
                        cluster_dfs.append(parsed)
                else:
                    logger.warning(
                        "Cluster %s (lat=%.3f, lon=%.3f, segments=%d) failed to fetch after %d attempts; segments remain missing/unknown.",
                        cluster.cluster_id,
                        cluster.latitude,
                        cluster.longitude,
                        len(cluster.segment_ids),
                        self.max_retries,
                    )
            except Exception as cluster_err:
                logger.warning(
                    "Cluster %s failed with exception: %s. Continuing with remaining clusters.",
                    cluster.cluster_id,
                    cluster_err,
                )

        if not cluster_dfs:
            logger.warning("No weather observations successfully fetched from Open-Meteo.")
            columns = ["segment_id", "obs_date"] + EXPECTED_DYNAMIC_FEATURES + ["source", "fetched_at", "quality_flag"]
            return pd.DataFrame(columns=columns)

        combined_df = pd.concat(cluster_dfs, ignore_index=True)

        if segment_filter:
            combined_df = combined_df[combined_df["segment_id"].isin(segment_filter)].copy()

        # Database-aware rolling history retrieval
        history_df = None
        if self.storage is not None:
            try:
                start_dt = pd.to_datetime(start_str).date()
                history_start = (start_dt - timedelta(days=6)).isoformat()
                history_end = (start_dt - timedelta(days=1)).isoformat()
                history_df = self.storage.get_observations(
                    start_date=history_start,
                    end_date=history_end,
                    source=self.provider_name,
                )
            except Exception as e:
                logger.warning("Could not retrieve weather history for rolling calculation: %s", e)

        # Compute rolling 3-day and 7-day precipitation sums matching week2b_process_weather.py
        final_df = compute_rolling_precipitation(
            combined_df,
            history_df=history_df,
            segment_col="segment_id",
            date_col="obs_date",
            precip_col="precip_mm",
            flag_incomplete=(self.storage is not None),
        )

        return final_df

