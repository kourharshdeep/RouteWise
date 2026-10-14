"""Regression baseline tests ensuring existing API endpoints maintain contracts."""
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from fastapi.testclient import TestClient
from src.api.app import app

client = TestClient(app)


def test_baseline_health():
    res = client.get("/api/health")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "ok"
    assert data["segment_count"] == 151
    assert data["available_dates_count"] == 1821
    assert "model_version" in data


def test_baseline_corridor_segments():
    res = client.get("/api/v1/corridor/segments")
    assert res.status_code == 200
    data = res.json()
    assert data["type"] == "FeatureCollection"
    assert data["total_segments"] == 151
    assert len(data["features"]) == 151
    first_feat = data["features"][0]
    assert "id" in first_feat
    assert "properties" in first_feat
    assert "geometry" in first_feat


def test_baseline_risk_dates():
    res = client.get("/api/v1/risk/dates")
    assert res.status_code == 200
    data = res.json()
    assert data["total_dates"] == 1821
    assert data["start_date"] == "2021-01-06"
    assert data["end_date"] == "2025-12-31"


def test_baseline_risk_benchmark():
    res = client.get("/api/v1/risk?date=2023-07-09")
    assert res.status_code == 200
    data = res.json()
    assert data["metadata"]["requested_date"] == "2023-07-09"
    assert len(data["segments"]) == 151
    assert "summary" in data
    assert data["summary"]["total_segments"] == 151


def test_baseline_journey_places():
    res = client.get("/api/v1/journey/places")
    assert res.status_code == 200
    places = res.json()
    assert len(places) >= 16
    place_names = [p["name"] for p in places]
    assert any("Ramban" in n for n in place_names)
    assert any("Banihal" in n for n in place_names)


def test_baseline_disruptions_stats():
    res = client.get("/api/v1/disruptions/stats")
    assert res.status_code == 200
    data = res.json()
    assert data["total_events"] >= 90
    assert "by_type" in data
    assert "top_locations" in data
