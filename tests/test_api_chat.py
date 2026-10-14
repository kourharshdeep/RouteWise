"""Tests for conversational AI assistant API endpoints."""
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from fastapi.testclient import TestClient
from src.api.app import app

client = TestClient(app)


def test_chat_query():
    payload = {
        "message": "What are the most dangerous segments on the highway?",
        "context": {
            "selected_date": "2023-07-09",
            "vehicle_type": "Truck",
            "origin": "Ramban",
            "destination": "Banihal",
        },
    }
    res = client.post("/api/v1/chat/query", json=payload)
    assert res.status_code == 200
    data = res.json()
    assert "reply" in data
    assert len(data["reply"]) > 20
    assert "suggested_followups" in data
    assert len(data["suggested_followups"]) > 0
    assert "source_engine" in data
