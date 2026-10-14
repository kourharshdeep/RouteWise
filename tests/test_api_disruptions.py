"""Tests for historical disruptions API endpoints."""
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from fastapi.testclient import TestClient
from src.api.app import app

client = TestClient(app)


def test_get_disruptions():
    res = client.get("/api/v1/disruptions?page_size=10")
    assert res.status_code == 200
    data = res.json()
    assert data["total"] > 0
    assert len(data["events"]) <= 10
    first = data["events"][0]
    assert "date" in first
    assert "disruption_type" in first


def test_get_disruption_stats():
    res = client.get("/api/v1/disruptions/stats")
    assert res.status_code == 200
    stats = res.json()
    assert stats["total_events"] > 0
    assert "landslide" in stats["by_type"]
    assert len(stats["top_locations"]) > 0
