"""Tests for authentication API endpoints."""
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from fastapi.testclient import TestClient
from src.api.app import app

client = TestClient(app)


def test_demo_accounts():
    res = client.get("/api/v1/auth/demo-accounts")
    assert res.status_code == 200
    data = res.json()
    assert len(data) >= 3
    assert any(u["email"] == "demo@routewise.ai" for u in data)


def test_login_demo_user():
    res = client.post(
        "/api/v1/auth/login",
        json={"email": "demo@routewise.ai", "password": "routewise2026"},
    )
    assert res.status_code == 200
    data = res.json()
    assert "access_token" in data
    assert data["user"]["email"] == "demo@routewise.ai"
    assert data["user"]["preferred_vehicle"] == "Car"

    # Test accessing protected /me endpoint
    token = data["access_token"]
    me_res = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert me_res.status_code == 200
    assert me_res.json()["email"] == "demo@routewise.ai"


def test_login_invalid_password():
    res = client.post(
        "/api/v1/auth/login",
        json={"email": "demo@routewise.ai", "password": "wrongpassword"},
    )
    assert res.status_code == 401


def test_register_new_user():
    import uuid
    test_email = f"test_{uuid.uuid4().hex[:6]}@routewise.ai"
    res = client.post(
        "/api/v1/auth/register",
        json={
            "email": test_email,
            "password": "securepassword123",
            "name": "Highway Specialist",
            "role": "logistics_operator",
            "preferred_vehicle": "Truck",
        },
    )
    assert res.status_code == 201
    data = res.json()
    assert data["user"]["email"] == test_email
    assert data["user"]["preferred_vehicle"] == "Truck"
    assert "access_token" in data


def test_guest_session():
    res = client.post("/api/v1/auth/guest")
    assert res.status_code == 200
    data = res.json()
    assert "access_token" in data
    assert data["user"]["role"] == "guest"
    assert data["user"]["name"] == "Guest Observer"

    # Test /me with guest token
    token = data["access_token"]
    me_res = client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert me_res.status_code == 200
    assert me_res.json()["role"] == "guest"


def test_guest_cannot_update_profile():
    # Issue guest token
    res = client.post("/api/v1/auth/guest")
    token = res.json()["access_token"]

    # Attempt to update profile
    update_res = client.put(
        "/api/v1/auth/profile",
        json={"name": "Hacker Guest", "preferred_vehicle": "Truck"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert update_res.status_code == 403
    assert "Guest users cannot modify account profile" in update_res.json()["detail"]


def test_login_throttle():
    throttle_email = "throttle_test@routewise.ai"
    # Execute 5 failed logins
    for _ in range(5):
        client.post(
            "/api/v1/auth/login",
            json={"email": throttle_email, "password": "wrongpassword"},
        )

    # 6th attempt should be throttled
    res = client.post(
        "/api/v1/auth/login",
        json={"email": throttle_email, "password": "wrongpassword"},
    )
    assert res.status_code == 429
    assert "Too many failed login attempts" in res.json()["detail"]
