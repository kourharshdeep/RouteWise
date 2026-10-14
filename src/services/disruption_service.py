"""Historical disruption query and analytics service.

Loads verified disruption records from data/disruption_log_snapped.csv,
supports filtering by date, year, type, and keyword, and computes corridor hazard statistics.
"""
from __future__ import annotations

import csv
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.api.config import settings
from src.api.schemas.disruptions import (
    DisruptionItem,
    DisruptionListResponse,
    DisruptionStats,
)


class DisruptionService:
    """Manages queries on historical corridor disruptions."""

    def __init__(self, log_path: Path | None = None) -> None:
        self.log_path = log_path or settings.disruptions_path
        self._events: List[DisruptionItem] = []
        self._load_data()

    def _load_data(self) -> None:
        if not self.log_path.exists():
            return

        with open(self.log_path, "r", encoding="utf-8", errors="replace") as f:
            reader = csv.DictReader(f)
            for idx, row in enumerate(reader, start=1):
                try:
                    dur_str = row.get("duration_hours", "").strip()
                    dur = float(dur_str) if dur_str else None
                except ValueError:
                    dur = None

                try:
                    snap_dist = float(row.get("snap_dist_m", 0.0))
                except (ValueError, TypeError):
                    snap_dist = None

                snap_ok_str = str(row.get("snap_ok", "")).lower()
                snap_ok = snap_ok_str in ("true", "1", "yes")

                try:
                    lat = float(row.get("lat", 0.0))
                    lon = float(row.get("lon", 0.0))
                except (ValueError, TypeError):
                    lat, lon = 33.3, 75.2

                self._events.append(
                    DisruptionItem(
                        id=idx,
                        date=row.get("date", "").strip(),
                        location_desc=row.get("location_desc", "").strip(),
                        lat=lat,
                        lon=lon,
                        location_confidence=row.get("location_confidence", "medium").strip(),
                        disruption_type=row.get("disruption_type", "unknown").strip(),
                        closure=row.get("closure", "full").strip(),
                        duration_hours=dur,
                        source_name=row.get("source_name", "Media Report").strip(),
                        source_url=row.get("source_url", "").strip() or None,
                        notes=row.get("notes", "").strip(),
                        segment_id=row.get("segment_id", "").strip() or None,
                        snap_dist_m=snap_dist,
                        snap_ok=snap_ok,
                    )
                )

    def get_disruptions(
        self,
        year: Optional[int] = None,
        disruption_type: Optional[str] = None,
        query: Optional[str] = None,
        closure: Optional[str] = None,
        page: int = 1,
        page_size: int = 20,
    ) -> DisruptionListResponse:
        filtered = self._events

        if year:
            filtered = [e for e in filtered if e.date.startswith(str(year))]

        if disruption_type and disruption_type != "all":
            dtype_lower = disruption_type.lower()
            filtered = [e for e in filtered if dtype_lower in e.disruption_type.lower()]

        if closure and closure != "all":
            cl_lower = closure.lower()
            filtered = [e for e in filtered if cl_lower in e.closure.lower()]

        if query:
            q = query.lower()
            filtered = [
                e for e in filtered
                if q in e.location_desc.lower()
                or q in e.notes.lower()
                or (e.segment_id and q in e.segment_id.lower())
            ]

        # Sort descending by date
        filtered.sort(key=lambda x: x.date, reverse=True)

        total = len(filtered)
        start_idx = (page - 1) * page_size
        end_idx = start_idx + page_size
        page_items = filtered[start_idx:end_idx]

        return DisruptionListResponse(
            total=total,
            page=page,
            page_size=page_size,
            events=page_items,
        )

    def get_stats(self) -> DisruptionStats:
        by_type = Counter(e.disruption_type for e in self._events)
        by_year = Counter(e.date[:4] for e in self._events if len(e.date) >= 4)

        # Hotspot locations
        locs = Counter(e.location_desc.split(" ")[0].replace("–", "-") for e in self._events)
        top_locs = [
            {"location": loc, "count": cnt}
            for loc, cnt in locs.most_common(8)
            if loc and len(loc) > 2
        ]

        return DisruptionStats(
            total_events=len(self._events),
            by_type=dict(by_type),
            by_year=dict(sorted(by_year.items())),
            top_locations=top_locs,
        )


disruption_service = DisruptionService()
