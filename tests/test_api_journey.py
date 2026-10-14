"""Tests for journey planning and routing API endpoints."""
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from fastapi.testclient import TestClient
from src.api.app import app

client = TestClient(app)


def test_get_places():
    res = client.get("/api/v1/journey/places")
    assert res.status_code == 200
    places = res.json()
    assert len(places) > 5
    names = [p["name"] for p in places]
    assert any("Ramban" in n for n in names)
    assert any("Banihal" in n for n in names)


def test_plan_journey():
    req = {
        "origin": "Ramban",
        "destination": "Banihal",
        "date": "2023-07-09",
        "departure_time": "08:30",
        "arrival_deadline": "12:00",
        "vehicle_type": "Truck",
    }
    res = client.post("/api/v1/journey/plan", json=req)
    assert res.status_code == 200
    data = res.json()
    assert data["origin"]
    assert data["destination"]
    assert data["total_distance_km"] > 0
    assert data["estimated_travel_minutes"] > 0
    assert data["vehicle_advisory"]["vehicle_type"] == "Truck"
    assert "itinerary" in data
    assert len(data["itinerary"]) > 0
