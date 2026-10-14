"""Unit tests for /api/v1/corridor endpoints."""
from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from fastapi.testclient import TestClient
from src.api.app import app

client = TestClient(app)


def test_get_corridor_segments_geojson() -> None:
    """Verifies that /api/v1/corridor/segments returns 151 GeoJSON LineStrings."""
    response = client.get("/api/v1/corridor/segments")
    assert response.status_code == 200
    data = response.json()

    assert data["type"] == "FeatureCollection"
    assert data["total_segments"] == 151
    assert data["crs"] == "EPSG:4326"
    assert len(data["features"]) == 151

    # Inspect first feature structure and coordinate ranges
    f0 = data["features"][0]
    assert f0["type"] == "Feature"
    assert "id" in f0
    geom = f0["geometry"]
    assert geom["type"] == "LineString"
    assert len(geom["coordinates"]) >= 2

    # Check coordinate bounds (Ramban-Banihal stretch: lat ~33.2 to 33.5, lon ~75.1 to 75.3)
    first_coord = geom["coordinates"][0]
    lon, lat = first_coord[0], first_coord[1]
    assert 75.0 <= lon <= 75.5, f"Longitude {lon} out of expected corridor range."
    assert 33.1 <= lat <= 33.6, f"Latitude {lat} out of expected corridor range."

    # Check properties
    props = f0["properties"]
    assert "length_m" in props
    assert "slope" in props
    assert "elevation_m" in props
    assert props["length_m"] > 0


def test_get_segment_features_drawer() -> None:
    """Verifies that /api/v1/corridor/segments/{id}/features returns genuine input features."""
    seg_id = "447079837_1077082205_0"
    res = client.get(f"/api/v1/corridor/segments/{seg_id}/features?date=2023-07-09")
    assert res.status_code == 200
    data = res.json()
    assert data["segment_id"] == seg_id
    assert data["date"] == "2023-07-09"
    assert data["length_m"] > 0
    assert data["slope_deg"] >= 0
    assert "Input features" in data["disclaimer"]
    assert data["weather"] is not None
    assert data["weather"]["precip_mm"] >= 0
    assert "ERA5-Land" in data["weather"]["data_source"]


def test_get_along_route_services() -> None:
    """Verifies along-route facilities endpoint."""
    res = client.get("/api/v1/corridor/services")
    assert res.status_code == 200
    services = res.json()
    assert len(services) >= 5
    types = {s["type"] for s in services}
    assert "hospital" in types
    assert "police" in types
    assert "fuel" in types
    assert all("source" in s and "verified" in s for s in services)


def test_get_official_advisories() -> None:
    """Verifies config-driven official traffic police contacts card."""
    res = client.get("/api/v1/corridor/advisories")
    assert res.status_code == 200
    data = res.json()
    assert "Traffic Police" in data["authority"]
    assert "official traffic advisories are the authority" in data["disclaimer"]
    assert len(data["control_units"]) >= 3
    unit_names = [u["unit"] for u in data["control_units"]]
    assert any("Ramban" in n for n in unit_names)


def test_get_corridor_weather() -> None:
    """Verifies corridor weather snapshot for historical date."""
    res = client.get("/api/v1/corridor/weather?date=2023-07-09")
    assert res.status_code == 200
    data = res.json()
    assert data["total_segments_covered"] == 151
    assert data["max_precipitation_mm"] >= 0
    assert "segments" in data

