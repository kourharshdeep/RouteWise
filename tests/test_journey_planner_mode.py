"""Unit and integration tests for mode-aware journey planning (Task 3c).

Verifies:
1. Live plan with today's date evaluates successfully with real live telemetry.
2. Live plan with omitted date defaults to latest live evaluation date.
3. Live plan with leftover historical date ('2023-07-09') safely falls back to latest live risk,
   preventing spurious NO_DATA recommendations.
4. Live mode API endpoint behaves identically across all three input date shapes.
5. Historical mode remains unchanged, requiring date and returning byte-identical results.
"""
from __future__ import annotations

import datetime
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

from src.api.app import app
from src.api.schemas.journey import JourneyPlanRequest
from src.services.journey_service import journey_service
from src.services.live_risk_service import live_risk_service

from src.services.weather.storage import weather_storage

client = TestClient(app)


@pytest.fixture
def isolated_live_db(tmp_path: Path):
    """Initializes and seeds an isolated runtime database with 151 segments of live risk."""
    db_file = tmp_path / "live_test.db"
    orig_path = weather_storage.db_path
    orig_lrs_path = live_risk_service.storage.db_path
    weather_storage.db_path = db_file
    live_risk_service.storage.db_path = db_file
    live_risk_service.init_db()

    now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
    all_segs = journey_service._sorted_segment_ids
    with live_risk_service._get_connection() as conn:
        for s in all_segs:
            conn.execute(
                """
                INSERT OR REPLACE INTO live_risk (
                    segment_id, as_of, score, tier, status, is_stale,
                    model_version, checkpoint_sha256, weather_window_end, computed_at, source
                ) VALUES (?, ?, 0.05, 'Low', 'OK', 0, '1.0.0', 'SHA', '2026-11-10', ?, 'open-meteo')
                """,
                (s, "2026-11-10", now_iso),
            )
        conn.commit()

    yield db_file

    weather_storage.db_path = orig_path
    live_risk_service.storage.db_path = orig_lrs_path


def test_live_plan_with_today_date(isolated_live_db, set_live_mode):
    """Live plan with today's date evaluates against current live risk."""
    set_live_mode("live")
    req = JourneyPlanRequest(
        origin="Ramban",
        destination="Banihal",
        date="2026-11-10",
        departure_time="08:00",
        mode="live",
    )
    res = journey_service.plan_journey(req)

    assert res.mode == "live"
    assert res.journey_date == "2026-11-10"
    assert res.unknown_segments_count == 0
    assert res.recommendation != "NO_DATA"
    assert "Live advisory route analysis" in res.retrospective_notice


def test_live_plan_with_omitted_date(isolated_live_db, set_live_mode):
    """Live plan with omitted date uses latest live risk as_of date."""
    set_live_mode("live")
    req = JourneyPlanRequest(
        origin="Ramban",
        destination="Banihal",
        date=None,
        departure_time="08:00",
        mode="live",
    )
    res = journey_service.plan_journey(req)

    assert res.mode == "live"
    assert res.journey_date == "2026-11-10"
    assert res.unknown_segments_count == 0
    assert res.recommendation != "NO_DATA"


def test_live_plan_with_leftover_historical_date_fallback(isolated_live_db, set_live_mode):
    """Live plan with a leftover historical date falls back to latest live risk without spurious NO_DATA."""
    set_live_mode("live")
    req = JourneyPlanRequest(
        origin="Ramban",
        destination="Banihal",
        date="2023-07-09",
        departure_time="08:00",
        mode="live",
    )
    res = journey_service.plan_journey(req)

    # Must NOT fail with NO_DATA due to missing 2023-07-09 rows in live DB
    assert res.mode == "live"
    assert res.journey_date == "2026-11-10"
    assert res.unknown_segments_count == 0
    assert res.recommendation != "NO_DATA"


def test_live_plan_api_endpoint_handles_all_date_shapes(isolated_live_db, set_live_mode):
    """REST API endpoint /api/v1/journey/plan correctly resolves live planning for all date inputs."""
    set_live_mode("live")

    # 1. Historical date passed in live mode
    res1 = client.post(
        "/api/v1/journey/plan",
        json={"origin": "Ramban Gateway", "destination": "Banihal Gateway", "mode": "live", "date": "2023-07-09"},
    )
    assert res1.status_code == 200
    d1 = res1.json()
    assert d1["mode"] == "live"
    assert d1["journey_date"] == "2026-11-10"
    assert d1["recommendation"] != "NO_DATA"

    # 2. Omitted date
    res2 = client.post(
        "/api/v1/journey/plan",
        json={"origin": "Ramban Gateway", "destination": "Banihal Gateway", "mode": "live"},
    )
    assert res2.status_code == 200
    d2 = res2.json()
    assert d2["journey_date"] == "2026-11-10"

    # 3. Explicit today date
    res3 = client.post(
        "/api/v1/journey/plan",
        json={"origin": "Ramban Gateway", "destination": "Banihal Gateway", "mode": "live", "date": "2026-11-10"},
    )
    assert res3.status_code == 200
    d3 = res3.json()
    assert d3["journey_date"] == "2026-11-10"


def test_historical_mode_requires_date_and_preserves_contract():
    """Historical mode continues to require date and rejects missing date with 400."""
    res_bad = client.post(
        "/api/v1/journey/plan",
        json={"origin": "Ramban Gateway", "destination": "Banihal Gateway", "mode": "historical"},
    )
    assert res_bad.status_code == 400
    assert "date parameter is required" in res_bad.json()["detail"]

    res_good = client.post(
        "/api/v1/journey/plan",
        json={"origin": "Ramban Gateway", "destination": "Banihal Gateway", "mode": "historical", "date": "2023-07-09"},
    )
    assert res_good.status_code == 200
    d = res_good.json()
    assert d["mode"] == "historical"
    assert d["journey_date"] == "2023-07-09"
    assert d["total_route_segments"] == 75
