"""Golden-output regression tests for journey planning (Step 2 safety net).

Verifies that journey planning responses remain strictly identical before and after
performance optimizations across:
- Historical mode (both directions, dates 2023-07-09 and 2024-03-15)
- Live mode (both directions with seeded live_risk, a CLOSED segment, and an UNKNOWN segment)
"""
from __future__ import annotations

import json
import sqlite3
import tempfile
from pathlib import Path
from typing import Any, Dict

import pytest

from src.api.schemas.journey import JourneyPlanRequest
from src.services.hazard_event_service import hazard_event_service
from src.services.journey_service import journey_service
from src.services.live_risk_service import live_risk_service
from src.services.weather.storage import weather_storage

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"


def _normalize_response(data: Dict[str, Any]) -> Dict[str, Any]:
    """Strips variable timing/timestamp metadata while preserving all substantive content."""
    cleaned = dict(data)
    # If any timing/timestamp fields exist that vary per run, standardize them here
    return cleaned


@pytest.mark.parametrize(
    "fixture_name,origin,destination,date_str",
    [
        ("golden_journey_historical_2023_07_09_forward.json", "Ramban Gateway", "Banihal Gateway", "2023-07-09"),
        ("golden_journey_historical_2023_07_09_reverse.json", "Banihal Gateway", "Ramban Gateway", "2023-07-09"),
        ("golden_journey_historical_2024_03_15_forward.json", "Ramban Gateway", "Banihal Gateway", "2024-03-15"),
        ("golden_journey_historical_2024_03_15_reverse.json", "Banihal Gateway", "Ramban Gateway", "2024-03-15"),
    ],
)
def test_historical_golden_output(fixture_name: str, origin: str, destination: str, date_str: str):
    """Historical journey plan responses must exactly match pre-optimization golden fixtures."""
    fixture_path = FIXTURES_DIR / fixture_name
    assert fixture_path.exists(), f"Fixture missing: {fixture_path}"

    with open(fixture_path, "r", encoding="utf-8") as f:
        expected = json.load(f)

    req = JourneyPlanRequest(
        origin=origin,
        destination=destination,
        date=date_str,
        mode="historical",
        vehicle_type="Car",
    )
    actual = journey_service.plan_journey(req).model_dump()

    assert _normalize_response(actual) == _normalize_response(expected)


@pytest.mark.parametrize(
    "fixture_name,origin,destination",
    [
        ("golden_journey_live_forward.json", "Ramban Gateway", "Banihal Gateway"),
        ("golden_journey_live_reverse.json", "Banihal Gateway", "Ramban Gateway"),
    ],
)
def test_live_golden_output_with_seeded_hazards(tmp_path: Path, fixture_name: str, origin: str, destination: str):
    """Live journey plan responses with CLOSED and UNKNOWN segments must match pre-optimization golden fixtures."""
    fixture_path = FIXTURES_DIR / fixture_name
    assert fixture_path.exists(), f"Fixture missing: {fixture_path}"

    with open(fixture_path, "r", encoding="utf-8") as f:
        expected = json.load(f)

    test_db = tmp_path / "golden_live.db"
    old_path = weather_storage.db_path
    try:
        weather_storage.db_path = test_db
        live_risk_service.init_db()
        hazard_event_service.init_db()

        all_segs = journey_service._sorted_segment_ids
        closed_seg = all_segs[50]
        unknown_seg = all_segs[60]

        records = []
        for s in all_segs:
            if s == unknown_seg:
                records.append((s, "2026-11-09", None, "UNKNOWN", "MISSING_DATA", 0, "1.0.0", "SHA", "2026-11-09", "2026-11-09T00:00:00Z"))
            else:
                records.append((s, "2026-11-09", 0.05, "Low", "OK", 0, "1.0.0", "SHA", "2026-11-09", "2026-11-09T00:00:00Z"))

        with sqlite3.connect(test_db) as conn:
            conn.executemany(
                """
                INSERT INTO live_risk (
                    segment_id, as_of, score, tier, status, is_stale,
                    model_version, checkpoint_sha256, weather_window_end, computed_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                records,
            )
            conn.commit()

        hazard_event_service.simulate_event(
            preset="landslide",
            segment_id=closed_seg,
            severity="critical",
            duration_hours=24,
            user_id=1,
        )

        req = JourneyPlanRequest(
            origin=origin,
            destination=destination,
            mode="live",
            vehicle_type="Car",
        )
        actual = journey_service.plan_journey(req).model_dump()

        assert _normalize_response(actual) == _normalize_response(expected)
    finally:
        weather_storage.db_path = old_path

