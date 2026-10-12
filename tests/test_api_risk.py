"""Unit tests for /api/v1/risk endpoints."""
from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from fastapi.testclient import TestClient
from src.api.app import app

client = TestClient(app)


def test_get_available_dates() -> None:
    """Verifies that /api/v1/risk/dates returns observation range boundaries."""
    response = client.get("/api/v1/risk/dates")
    assert response.status_code == 200
    data = response.json()

    assert data["start_date"] == "2021-01-06"
    assert data["end_date"] == "2025-12-31"
    assert data["total_dates"] == 1821
    assert len(data["sample_dates"]) > 0
    assert "retrospective" in data["description"].lower()


def test_get_risk_valid_date() -> None:
    """Verifies that /api/v1/risk?date=2023-07-09 returns 151 typed predictions."""
    response = client.get("/api/v1/risk?date=2023-07-09")
    assert response.status_code == 200
    data = response.json()

    # 1. Metadata checks
    meta = data["metadata"]
    assert meta["dataset_type"] == "retrospective_historical_backtest"
    assert meta["is_live_operational_forecast"] is False
    assert meta["prediction_horizon_hours"] == 24
    assert meta["model_version"] == "68b04504eae6062c"
    assert meta["requested_date"] == "2023-07-09"
    assert "advisory" in meta["advisory_notice"].lower()

    # 2. Summary checks
    summary = data["summary"]
    assert summary["total_segments"] == 151
    assert (
        summary["high_risk_count"]
        + summary["medium_risk_count"]
        + summary["low_risk_count"]
        + summary["unknown_count"]
        == 151
    )

    # 3. Segments list checks
    segments = data["segments"]
    assert len(segments) == 151
    first_seg = segments[0]
    assert "segment_id" in first_seg
    assert first_seg["risk_tier"] in ("Low", "Medium", "High", "UNKNOWN")
    assert first_seg["status"] in ("OK", "MISSING_DATA", "STALE_DATA")
    if first_seg["status"] == "OK":
        assert 0.0 <= first_seg["risk_score"] <= 1.0


def test_get_risk_missing_date_query_param() -> None:
    """Verifies that omitting ?date query parameter returns HTTP 422 Unprocessable Entity."""
    response = client.get("/api/v1/risk")
    assert response.status_code == 422


def test_get_risk_invalid_date_format() -> None:
    """Verifies that malformed date returns HTTP 400 Bad Request."""
    response = client.get("/api/v1/risk?date=not-a-date")
    assert response.status_code == 400
    assert "Invalid date format" in response.json()["detail"]


def test_get_risk_out_of_range_date() -> None:
    """Verifies that requesting a date outside the supported historical window returns HTTP 404."""
    response = client.get("/api/v1/risk?date=2020-01-01")
    assert response.status_code == 404
    assert "outside the supported historical window" in response.json()["detail"]
