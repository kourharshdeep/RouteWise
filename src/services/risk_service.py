"""Risk prediction retrieval service.

Exposes precomputed historical risk forecasts from cache/precomputed_risk_cache.json.
Provides fast in-memory lookups (<1ms) while preserving model metadata and honest semantics.
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import HTTPException, status

from src.api.config import settings
from src.api.schemas.risk import (
    AvailableDatesResponse,
    CorridorRiskResponse,
    RiskMetadata,
    RiskSummary,
    SegmentRiskItem,
)


class RiskService:
    """Manages risk forecast retrieval from the precomputed cache."""

    def __init__(self, cache_path: Path | None = None) -> None:
        self.cache_path = cache_path or settings.risk_cache_path
        self._cache_data: Optional[Dict[str, Any]] = None
        self._load_cache()

    def _load_cache(self) -> None:
        """Loads the precomputed risk cache into memory."""
        if not self.cache_path.exists():
            raise FileNotFoundError(
                f"Risk cache file not found at: {self.cache_path}. "
                "Ensure scripts/precompute_risk.py was executed."
            )
        with open(self.cache_path, "r", encoding="utf-8") as f:
            self._cache_data = json.load(f)

    @property
    def is_available(self) -> bool:
        return self._cache_data is not None

    def get_metadata(self) -> Dict[str, Any]:
        if not self._cache_data:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Risk cache data is not loaded.",
            )
        return self._cache_data.get("metadata", {})

    def get_available_dates(self) -> AvailableDatesResponse:
        """Returns the start/end dates and total available observation dates."""
        meta = self.get_metadata()
        daily = self._cache_data.get("daily_predictions", {})
        all_dates = sorted(daily.keys())

        if not all_dates:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="No historical observation dates found in risk cache.",
            )

        # Include sample reference dates across monsoon, winter, and summer
        sample_candidates = ["2021-07-15", "2022-01-20", "2023-07-09", "2024-03-15", "2025-08-10"]
        samples = [d for d in sample_candidates if d in daily] or all_dates[:5]

        return AvailableDatesResponse(
            start_date=all_dates[0],
            end_date=all_dates[-1],
            total_dates=len(all_dates),
            sample_dates=samples,
        )

    def get_risk_by_date(self, date_str: str) -> CorridorRiskResponse:
        """Retrieves corridor risk predictions for a specific observation date.
        
        Args:
            date_str: Date string in 'YYYY-MM-DD' format.
            
        Returns:
            CorridorRiskResponse containing metadata, summary breakdown, and 151 segment predictions.
        """
        # 1. Validate date format
        try:
            parsed_date = datetime.strptime(date_str, "%Y-%m-%d").date()
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid date format '{date_str}'. Expected format is 'YYYY-MM-DD'.",
            )

        # 2. Check cache availability
        if not self._cache_data:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Risk cache is currently unavailable.",
            )

        daily = self._cache_data.get("daily_predictions", {})
        if date_str not in daily:
            all_dates = sorted(daily.keys())
            start_d = all_dates[0] if all_dates else "N/A"
            end_d = all_dates[-1] if all_dates else "N/A"
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=(
                    f"Observation date '{date_str}' is outside the supported historical window. "
                    f"Available range is from {start_d} to {end_d}."
                ),
            )

        # 3. Build segment predictions and tally summary
        day_preds = daily[date_str]
        segment_items: List[SegmentRiskItem] = []
        high_count = 0
        med_count = 0
        low_count = 0
        unknown_count = 0

        for seg_id, item in day_preds.items():
            score = item.get("risk_score")
            tier = item.get("risk_tier", "UNKNOWN")
            stat = item.get("status", "OK")

            if tier == "High":
                high_count += 1
            elif tier == "Medium":
                med_count += 1
            elif tier == "Low":
                low_count += 1
            else:
                unknown_count += 1

            segment_items.append(
                SegmentRiskItem(
                    segment_id=seg_id,
                    risk_score=score,
                    risk_tier=tier,
                    status=stat,
                    is_stale=stat == "STALE_DATA",
                )
            )

        meta_dict = self.get_metadata()
        metadata = RiskMetadata(
            dataset_type=meta_dict.get("dataset_type", "retrospective_historical_backtest"),
            meteorological_source=meta_dict.get("meteorological_source", "ERA5-Land reanalysis via Copernicus CDS"),
            is_live_operational_forecast=False,
            prediction_horizon_hours=meta_dict.get("prediction_horizon_hours", 24),
            model_version=meta_dict.get("model_version", "unknown"),
            thresholds=meta_dict.get("thresholds", {"tau_med": 0.10, "tau_high": 0.35}),
            requested_date=date_str,
            generated_at=meta_dict.get("generated_at", datetime.utcnow().isoformat()),
        )

        summary = RiskSummary(
            total_segments=len(segment_items),
            high_risk_count=high_count,
            medium_risk_count=med_count,
            low_risk_count=low_count,
            unknown_count=unknown_count,
        )

        return CorridorRiskResponse(
            metadata=metadata,
            summary=summary,
            segments=segment_items,
        )


risk_service = RiskService()
