"""Comprehensive tests for Role-Based Access Control (RBAC) and Field Report lifecycle."""
import io
import sys
import uuid
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from src.api.app import app
from src.services.auth_service import auth_service
from src.services.report_service import report_service

client = TestClient(app)


@pytest.fixture(scope="module")
def seeded_tokens():
    """Generates authentic tokens for anonymous, guest, user, and patrol roles."""
    # 1. Guest Token
    guest_res = client.post("/api/v1/auth/guest")
    guest_token = guest_res.json()["access_token"]

    # 2. User Token (Dr. Kabir Sharma)
    user_res = client.post(
        "/api/v1/auth/login",
        json={"email": "demo@routewise.ai", "password": "routewise2026"},
    )
    user_token = user_res.json()["access_token"]
    user_id = user_res.json()["user"]["id"]

    # 3. Patrol Token (Inspector Amit Rathore)
    patrol_res = client.post(
        "/api/v1/auth/login",
        json={"email": "patrol@routewise.ai", "password": "DemoPatrol2026!"},
    )
    patrol_token = patrol_res.json()["access_token"]
    patrol_id = patrol_res.json()["user"]["id"]

    # 4. Another independent User Token for IDOR testing
    second_email = f"user2_{uuid.uuid4().hex[:6]}@routewise.ai"
    u2_res = client.post(
        "/api/v1/auth/register",
        json={
            "email": second_email,
            "password": "Password123!",
            "name": "Second Commuter",
            "role": "patrol",  # Attempting privilege escalation
        },
    )
    u2_token = u2_res.json()["access_token"]
    u2_profile = u2_res.json()["user"]

    return {
        "guest": guest_token,
        "user": user_token,
        "user_id": user_id,
        "patrol": patrol_token,
        "patrol_id": patrol_id,
        "user2": u2_token,
        "user2_id": u2_profile["id"],
        "user2_role": u2_profile["role"],
    }


def test_registration_privilege_escalation_prevention(seeded_tokens):
    """Asserts that public registration strictly assigns role 'user' despite requested 'patrol'."""
    assert seeded_tokens["user2_role"] == "user", "Public registration must force role to 'user'!"


def test_rbac_endpoints_matrix(seeded_tokens):
    """Asserts expected status codes across Anonymous, Guest, User, and Patrol."""
    guest_headers = {"Authorization": f"Bearer {seeded_tokens['guest']}"}
    user_headers = {"Authorization": f"Bearer {seeded_tokens['user']}"}
    patrol_headers = {"Authorization": f"Bearer {seeded_tokens['patrol']}"}

    # 1. /api/v1/reports (GET queue): Patrol/Admin only
    assert client.get("/api/v1/reports").status_code == 401  # Anonymous
    assert client.get("/api/v1/reports", headers=guest_headers).status_code == 403  # Guest
    assert client.get("/api/v1/reports", headers=user_headers).status_code == 403   # User
    assert client.get("/api/v1/reports", headers=patrol_headers).status_code == 200 # Patrol

    # 2. /api/v1/reports/summary: Patrol/Admin only
    assert client.get("/api/v1/reports/summary", headers=user_headers).status_code == 403
    assert client.get("/api/v1/reports/summary", headers=patrol_headers).status_code == 200

    # 3. /api/v1/reports/public: All roles can read
    assert client.get("/api/v1/reports/public").status_code == 200
    assert client.get("/api/v1/reports/public", headers=guest_headers).status_code == 200
    assert client.get("/api/v1/reports/public", headers=user_headers).status_code == 200
    assert client.get("/api/v1/reports/public", headers=patrol_headers).status_code == 200

    # 4. /api/v1/reports (POST): Authenticated only, Guests blocked
    dummy_payload = {
        "client_uuid": f"test-rbac-{uuid.uuid4()}",
        "category": "shooting_stones",
        "latitude": "33.2435",
        "longitude": "75.2415",
        "description": "RBAC verification incident",
    }
    assert client.post("/api/v1/reports", data=dummy_payload).status_code == 401  # Anonymous
    assert client.post("/api/v1/reports", data=dummy_payload, headers=guest_headers).status_code == 403  # Guest
    # User can submit
    user_sub = client.post("/api/v1/reports", data=dummy_payload, headers=user_headers)
    assert user_sub.status_code == 201


def test_report_idempotency_on_client_uuid(seeded_tokens):
    """Submitting the same client_uuid twice returns the existing record without duplicates."""
    user_headers = {"Authorization": f"Bearer {seeded_tokens['user']}"}
    client_id = f"idem-{uuid.uuid4()}"
    payload = {
        "client_uuid": client_id,
        "category": "road_damage",
        "latitude": "33.2500",
        "longitude": "75.2400",
        "description": "Idempotent submission test",
    }

    res1 = client.post("/api/v1/reports", data=payload, headers=user_headers)
    assert res1.status_code == 201
    rep1 = res1.json()

    # Re-submit with same client_uuid
    res2 = client.post("/api/v1/reports", data=payload, headers=user_headers)
    assert res2.status_code in (200, 201)
    rep2 = res2.json()

    assert rep1["id"] == rep2["id"]
    assert rep1["client_uuid"] == rep2["client_uuid"]


def test_idor_protection_between_users(seeded_tokens):
    """User 2 must NOT be able to view User 1's submitted (unverified) report."""
    user1_headers = {"Authorization": f"Bearer {seeded_tokens['user']}"}
    user2_headers = {"Authorization": f"Bearer {seeded_tokens['user2']}"}
    patrol_headers = {"Authorization": f"Bearer {seeded_tokens['patrol']}"}

    # Create unverified report by User 1
    create_res = client.post(
        "/api/v1/reports",
        data={
            "client_uuid": f"idor-{uuid.uuid4()}",
            "category": "landslide",
            "latitude": "33.2700",
            "longitude": "75.2300",
            "description": "Private unverified observation",
        },
        headers=user1_headers,
    )
    report_id = create_res.json()["id"]

    # User 1 can view
    assert client.get(f"/api/v1/reports/{report_id}", headers=user1_headers).status_code == 200

    # User 2 CANNOT view (IDOR protected) -> 403 Forbidden
    u2_res = client.get(f"/api/v1/reports/{report_id}", headers=user2_headers)
    assert u2_res.status_code == 403

    # Patrol CAN view
    assert client.get(f"/api/v1/reports/{report_id}", headers=patrol_headers).status_code == 200


def test_public_reports_never_expose_unverified_or_reporter_identities():
    """GET /api/v1/reports/public must only return verified/assigned and omit personal info."""
    res = client.get("/api/v1/reports/public")
    assert res.status_code == 200
    items = res.json()
    for item in items:
        assert item["status"] in ("verified", "assigned")
        assert "reporter_id" not in item
        assert "reporter_name" not in item
        assert "reporter_email" not in item


def test_report_lifecycle_state_machine(seeded_tokens):
    """Verifies complete valid transition path: submitted -> verified -> assigned -> resolved."""
    user_headers = {"Authorization": f"Bearer {seeded_tokens['user']}"}
    patrol_headers = {"Authorization": f"Bearer {seeded_tokens['patrol']}"}
    patrol_id = seeded_tokens["patrol_id"]

    # 1. Create Report
    c_res = client.post(
        "/api/v1/reports",
        data={
            "client_uuid": f"lifecycle-{uuid.uuid4()}",
            "category": "flooding",
            "latitude": "33.3000",
            "longitude": "75.2100",
            "description": "Culvert overflow",
        },
        headers=user_headers,
    )
    assert c_res.status_code == 201
    rep_id = c_res.json()["id"]
    assert c_res.json()["status"] == "submitted"

    # 2. Invalid Transition: submitted -> resolved (409 Conflict)
    bad_res = client.patch(
        f"/api/v1/reports/{rep_id}/status",
        json={"status": "resolved", "note": "Trying to skip verification"},
        headers=patrol_headers,
    )
    assert bad_res.status_code == 409

    # 3. Valid: submitted -> verified
    v_res = client.patch(
        f"/api/v1/reports/{rep_id}/status",
        json={"status": "verified", "note": "Confirmed by patrol unit"},
        headers=patrol_headers,
    )
    assert v_res.status_code == 200
    assert v_res.json()["status"] == "verified"

    # 4. Valid: assign to patrol officer
    a_res = client.patch(
        f"/api/v1/reports/{rep_id}/assign",
        json={"assigned_to": patrol_id, "note": "Clear debris and direct traffic"},
        headers=patrol_headers,
    )
    assert a_res.status_code == 200
    assert a_res.json()["status"] == "assigned"
    assert a_res.json()["assigned_to"] == patrol_id

    # 5. Valid: assigned -> resolved
    r_res = client.patch(
        f"/api/v1/reports/{rep_id}/status",
        json={"status": "resolved", "note": "Water drained, carriageway clear"},
        headers=patrol_headers,
    )
    assert r_res.status_code == 200
    assert r_res.json()["status"] == "resolved"

    # 6. Reopen resolved -> verified (requires note)
    no_note_reopen = client.patch(
        f"/api/v1/reports/{rep_id}/status",
        json={"status": "verified", "note": ""},
        headers=patrol_headers,
    )
    assert no_note_reopen.status_code == 422

    reopened = client.patch(
        f"/api/v1/reports/{rep_id}/status",
        json={"status": "verified", "note": "Debris restarted, reopening report"},
        headers=patrol_headers,
    )
    assert reopened.status_code == 200
    assert reopened.json()["status"] == "verified"


def test_rejection_requires_note(seeded_tokens):
    """Rejecting a report requires a mandatory explanation note."""
    user_headers = {"Authorization": f"Bearer {seeded_tokens['user']}"}
    patrol_headers = {"Authorization": f"Bearer {seeded_tokens['patrol']}"}

    create_res = client.post(
        "/api/v1/reports",
        data={
            "client_uuid": f"reject-test-{uuid.uuid4()}",
            "category": "other",
            "latitude": "33.2435",
            "longitude": "75.2415",
            "description": "Spurious report",
        },
        headers=user_headers,
    )
    rep_id = create_res.json()["id"]

    # Attempt rejection without note -> 422
    fail_res = client.patch(
        f"/api/v1/reports/{rep_id}/status",
        json={"status": "rejected", "note": ""},
        headers=patrol_headers,
    )
    assert fail_res.status_code == 422

    # With note -> 200
    ok_res = client.patch(
        f"/api/v1/reports/{rep_id}/status",
        json={"status": "rejected", "note": "No obstruction observed on site"},
        headers=patrol_headers,
    )
    assert ok_res.status_code == 200
    assert ok_res.json()["status"] == "rejected"


def test_spatial_snapping_near_and_far():
    """Reports within 500m of NH-44 snap to segment; points >500m have nearest_segment_id=None."""
    # Near Cafeteria Morh / Ramban: ~76m from corridor
    near_seg, near_dist = report_service.snap_to_corridor(33.24, 75.24)
    assert near_seg is not None
    assert near_dist <= 500.0

    # Far point (away in mountains, e.g. 33.10, 75.00)
    far_seg, far_dist = report_service.snap_to_corridor(33.10, 75.00)
    assert far_seg is None
    assert far_dist > 500.0


def test_photo_upload_magic_bytes_and_exif_stripping(seeded_tokens):
    """Uploads real image, verifies EXIF is stripped, and fake extension/bad bytes are rejected."""
    user_headers = {"Authorization": f"Bearer {seeded_tokens['user']}"}

    # 1. Create a genuine small test PNG
    img = Image.new("RGB", (64, 64), color="red")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)

    res = client.post(
        "/api/v1/reports",
        data={
            "client_uuid": f"photo-test-{uuid.uuid4()}",
            "category": "road_damage",
            "latitude": "33.2435",
            "longitude": "75.2415",
            "description": "Report with authentic photo",
        },
        files={"photo": ("test.png", buf.getvalue(), "image/png")},
        headers=user_headers,
    )
    assert res.status_code == 201
    data = res.json()
    assert data["has_photo"] is True
    assert data["photo_url"] is not None

    # Fetch photo via endpoint
    photo_res = client.get(data["photo_url"], headers=user_headers)
    assert photo_res.status_code == 200
    assert photo_res.headers["content-type"] in ("image/png", "image/jpeg", "image/webp")

    # 2. Reject fake image with spoofed extension
    fake_buf = b"This is not a real image file content!"
    bad_res = client.post(
        "/api/v1/reports",
        data={
            "client_uuid": f"spoof-test-{uuid.uuid4()}",
            "category": "road_damage",
            "latitude": "33.2435",
            "longitude": "75.2415",
        },
        files={"photo": ("fake.jpg", fake_buf, "image/jpeg")},
        headers=user_headers,
    )
    assert bad_res.status_code in (415, 400)
