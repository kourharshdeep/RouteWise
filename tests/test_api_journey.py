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


def test_ramban_to_banihal_contiguous_distance():
    """Distance between Ramban and Banihal equals the sum of contiguous segment lengths and <= corridor total."""
    for dt in ["2023-07-09", "2024-03-15"]:
        res = client.post(
            "/api/v1/journey/plan",
            json={"origin": "Ramban Gateway", "destination": "Banihal Gateway", "date": dt},
        )
        assert res.status_code == 200
        data = res.json()
        # 75 contiguous chainage segments
        assert data["total_route_segments"] == 75
        assert data["total_distance_km"] == 243.32
        assert data["total_distance_km"] <= 294.18  # Never exceeds corridor total of 294.18 km
        assert "Estimated transit time calculated from assumed vehicle speeds" in data["travel_time_disclaimer"]


def test_journey_direction_symmetry():
    """Ramban to Banihal must equal Banihal to Ramban in distance and segment count."""
    res_fwd = client.post(
        "/api/v1/journey/plan",
        json={"origin": "Ramban Gateway", "destination": "Banihal Gateway", "date": "2023-07-09"},
    )
    res_rev = client.post(
        "/api/v1/journey/plan",
        json={"origin": "Banihal Gateway", "destination": "Ramban Gateway", "date": "2023-07-09"},
    )
    assert res_fwd.status_code == 200
    assert res_rev.status_code == 200
    fwd = res_fwd.json()
    rev = res_rev.json()
    assert fwd["total_distance_km"] == rev["total_distance_km"] == 243.32
    assert fwd["total_route_segments"] == rev["total_route_segments"] == 75


def test_out_of_range_date_returns_404():
    """Date outside risk cache must return 404 with available date range, not substitute date."""
    res = client.post(
        "/api/v1/journey/plan",
        json={"origin": "Ramban Gateway", "destination": "Banihal Gateway", "date": "1999-01-01"},
    )
    assert res.status_code == 404
    detail = res.json()["detail"]
    assert "outside the supported historical window" in detail
    assert "Available range is from" in detail


def test_missing_risk_gives_unknown_not_low(monkeypatch):
    """Missing risk data must be marked as UNKNOWN, never defaulted to Low/0.05."""
    from src.services.risk_service import risk_service
    from src.api.schemas.risk import CorridorRiskResponse, RiskMetadata, RiskSummary, SegmentRiskItem

    # Create mock response where all segments have None risk score
    orig_get_risk = risk_service.get_risk_by_date

    def mock_get_risk(date_str):
        real_resp = orig_get_risk(date_str)
        # Empty segment risks
        empty_segs = [
            SegmentRiskItem(segment_id=s.segment_id, risk_score=None, risk_tier="UNKNOWN", status="MISSING")
            for s in real_resp.segments
        ]
        return CorridorRiskResponse(
            metadata=real_resp.metadata,
            summary=real_resp.summary,
            segments=empty_segs,
        )

    monkeypatch.setattr(risk_service, "get_risk_by_date", mock_get_risk)

    res = client.post(
        "/api/v1/journey/plan",
        json={"origin": "Ramban Gateway", "destination": "Banihal Gateway", "date": "2023-07-09"},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["unknown_segments_count"] == 75
    assert data["is_incomplete_data"] is True
    assert data["overall_route_risk"] == "Unknown"
    assert data["max_risk_score"] is None
    assert data["average_risk_score"] is None
    for item in data["itinerary"]:
        assert item["risk_tier"] == "UNKNOWN"
        assert item["risk_score"] is None


def test_no_four_point_five_km_floor():
    """Short distances must reflect genuine segment lengths without artificial 4.5 km floor."""
    from src.services.journey_service import journey_service
    # Test with a single segment slice
    saved_ids = journey_service._sorted_segment_ids
    try:
        # Pick one short segment
        first_seg_id = saved_ids[0]
        geojson = client.get("/api/v1/corridor/segments").json()
        feat = next(f for f in geojson["features"] if f["id"] == first_seg_id)
        real_len_km = round(feat["properties"]["length_m"] / 1000.0, 2)
        assert real_len_km < 4.5

        # Temporarily restrict sorted ids to 1 segment to simulate minimal route
        journey_service._sorted_segment_ids = [first_seg_id]
        res = client.post(
            "/api/v1/journey/plan",
            json={"origin": "Ramban Gateway", "destination": "Banihal Gateway", "date": "2023-07-09"},
        )
        assert res.status_code == 200
        data = res.json()
        assert data["total_distance_km"] == real_len_km
        assert data["total_distance_km"] != 4.5
    finally:
        journey_service._sorted_segment_ids = saved_ids


def test_all_151_segments_have_static_properties():
    """All 151 segments in corridor must have length_m, slope, elevation_m, and highway without nulls."""
    res = client.get("/api/v1/corridor/segments")
    assert res.status_code == 200
    features = res.json()["features"]
    assert len(features) == 151
    for feat in features:
        props = feat["properties"]
        assert props["length_m"] is not None and props["length_m"] > 0
        assert props["slope"] is not None
        assert props["elevation_m"] is not None and props["elevation_m"] > 0
        assert props["highway"] is not None and len(props["highway"]) > 0

