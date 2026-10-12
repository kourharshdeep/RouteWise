"""Unit tests for /api/health endpoint."""
from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from fastapi.testclient import TestClient
from src.api.app import app

client = TestClient(app)


def test_health_endpoint() -> None:
    """Verifies that /api/health returns HTTP 200 and matches HealthCheckResponse schema."""
    response = client.get("/api/health")
    assert response.status_code == 200
    data = response.json()

    assert data["status"] == "ok"
    assert data["service"] == "RouteWise Predictive Disruption API"
    assert data["version"] == "1.0.0-w8"
    assert data["model_version"] == "68b04504eae6062c"
    assert data["segment_count"] == 151
    assert data["cache_available"] is True
    assert data["available_dates_count"] == 1821
    assert "timestamp" in data


def test_root_endpoint() -> None:
    """Verifies that root / redirects or provides basic service links."""
    response = client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert "docs" in data
    assert "health" in data
