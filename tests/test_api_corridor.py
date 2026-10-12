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
