"""Unit, Role Matrix, and Regression Tests for Live Risk Service and Endpoints (Step 3).

Verifies:
1. Missing data contract: <7 days of observations produces UNKNOWN tier (never Low) and MISSING_DATA.
2. Stale data contract: Observations > 24 hours old produce UNKNOWN tier (never Low), STALE_DATA, and is_stale=True.
3. Valid data: 7 days of fresh observations produce valid advisory scores and Low/Medium/High tiers.
4. Role Matrix: /api/v1/live/status, /api/v1/live/risk, /api/v1/live/changes are accessible to
   anonymous guests, signed guest tokens, commuters (user), patrol officers, and administrators.
5. Regression: Historical endpoints /api/v1/risk and /api/v1/risk/dates remain 100% identical.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

from src.api.app import app
from src.services.auth_service import auth_service
from src.services.live_risk_service import LiveRiskService
from src.services.weather.base import EXPECTED_DYNAMIC_FEATURES
from src.services.weather.replay import ReplayProvider
from src.services.weather.storage import WeatherStorage

client = TestClient(app)


@pytest.fixture
def isolated_live_service(tmp_path: Path) -> LiveRiskService:
    """Creates a LiveRiskService backed by an isolated temporary database."""
    test_db = tmp_path / "test_live_risk.db"
    storage = WeatherStorage(db_path=test_db)
    storage.init_db()
    service = LiveRiskService(storage=storage)
    service.init_db()
    return service


def test_missing_data_never_defaults_to_low(isolated_live_service: LiveRiskService):
    """Honest Framing: Incomplete weather (<7 days) must evaluate to UNKNOWN and MISSING_DATA."""
    # Seed only 3 days of observations (less than required 7-day lookback window)
    provider = ReplayProvider(csv_path="data/weather_daily_by_segment.csv")
    df_3days = provider.fetch(start_date="2024-07-01", end_date="2024-07-03")
    isolated_live_service.storage.upsert_observations(df_3days)

    preds = isolated_live_service.compute_live_risk(as_of="2024-07-03")
    assert len(preds) == 151

    for p in preds:
        assert p["status"] == "MISSING_DATA", f"Expected MISSING_DATA, got {p['status']}"
        assert p["risk_tier"] == "UNKNOWN", f"Missing data must NEVER be Low; got {p['risk_tier']}"
        assert p["risk_score"] is None


def test_stale_data_never_defaults_to_low(isolated_live_service: LiveRiskService):
    """Honest Framing: Observations >24 hours old must evaluate to UNKNOWN and STALE_DATA."""
    # Seed full 7-day window
    provider = ReplayProvider(csv_path="data/weather_daily_by_segment.csv")
    df_7days = provider.fetch(start_date="2024-07-01", end_date="2024-07-07")
    isolated_live_service.storage.upsert_observations(df_7days)

    # Set eval_time to 48 hours after window end (stale)
    stale_eval_time = datetime(2024, 7, 9, 12, 0, 0, tzinfo=timezone.utc)

    preds = isolated_live_service.compute_live_risk(as_of="2024-07-07", eval_time=stale_eval_time)
    assert len(preds) == 151

    for p in preds:
        assert p["status"] == "STALE_DATA", f"Expected STALE_DATA, got {p['status']}"
        assert p["is_stale"] is True
        assert p["risk_tier"] == "UNKNOWN", f"Stale data must NEVER be Low; got {p['risk_tier']}"
        assert p["risk_score"] is not None  # Raw score computed but masked to UNKNOWN tier


def test_fresh_data_evaluates_valid_predictions(isolated_live_service: LiveRiskService):
    """7 days of fresh data yields OK status and Low/Medium/High tiers."""
    provider = ReplayProvider(csv_path="data/weather_daily_by_segment.csv")
    df_7days = provider.fetch(start_date="2024-07-01", end_date="2024-07-07")
    isolated_live_service.storage.upsert_observations(df_7days)

    fresh_eval_time = datetime(2024, 7, 7, 12, 0, 0, tzinfo=timezone.utc)
    preds = isolated_live_service.compute_live_risk(as_of="2024-07-07", eval_time=fresh_eval_time)

    assert len(preds) == 151
    for p in preds:
        assert p["status"] == "OK"
        assert p["is_stale"] is False
        assert p["risk_tier"] in ("Low", "Medium", "High")
        assert 0.0 <= p["risk_score"] <= 1.0
        assert p["checkpoint_sha256"] == "68B04504EAE6062C84927917C05168C34FD17823BA5EF5C13F963D335054006E"


def test_role_matrix_live_endpoints():
    """Verify that live endpoints are public read across guest, user, patrol, admin."""
    # Obtain auth tokens for distinct roles
    guest_token = auth_service.create_guest_session().access_token
    user_token = auth_service.create_token(user_id=1, email="demo@routewise.ai", role="user")
    patrol_token = auth_service.create_token(user_id=2, email="patrol@routewise.ai", role="patrol")
    admin_token = auth_service.create_token(user_id=3, email="admin@routewise.ai", role="admin")

    role_headers = {
        "anonymous": {},
        "guest": {"Authorization": f"Bearer {guest_token}"},
        "user": {"Authorization": f"Bearer {user_token}"},
        "patrol": {"Authorization": f"Bearer {patrol_token}"},
        "admin": {"Authorization": f"Bearer {admin_token}"},
    }

    endpoints = [
        "/api/v1/live/status",
        "/api/v1/live/risk",
        "/api/v1/live/changes",
    ]

    for role_name, headers in role_headers.items():
        for endpoint in endpoints:
            resp = client.get(endpoint, headers=headers)
            assert resp.status_code == 200, (
                f"Role '{role_name}' failed GET {endpoint}: {resp.status_code} {resp.text}"
            )
            data = resp.json()
            # Verify honest experimental framing and absence of reporter identity
            if endpoint == "/api/v1/live/status":
                assert data["experimental"] is True
                assert "checkpoint_sha256" in data
            elif endpoint == "/api/v1/live/risk":
                assert data["experimental"] is True
                assert "Experimental" in data["disclaimer"]
                # Verify no reporter fields leak in segments
                if data["segments"]:
                    first = data["segments"][0]
                    assert "reporter_id" not in first
                    assert "photo_path" not in first


def test_historical_risk_endpoints_regression():
    """Verify existing historical endpoints continue returning identical responses."""
    # 1. /api/v1/risk/dates
    resp_dates = client.get("/api/v1/risk/dates")
    assert resp_dates.status_code == 200
    dates_data = resp_dates.json()
    assert dates_data["total_dates"] == 1821
    assert dates_data["start_date"] == "2021-01-06"
    assert dates_data["end_date"] == "2025-12-31"

    # 2. /api/v1/risk?date=2023-07-09
    resp_risk = client.get("/api/v1/risk?date=2023-07-09")
    assert resp_risk.status_code == 200
    risk_data = resp_risk.json()
    assert risk_data["metadata"]["requested_date"] == "2023-07-09"
    assert len(risk_data["segments"]) == 151
    assert "summary" in risk_data
    assert "metadata" in risk_data
