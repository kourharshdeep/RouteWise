"""Corridor road network topology and GeoJSON service.

Parses the OpenStreetMap corridor graph from nh44_corridor_graph.graphml,
reprojects projected UTM 43N (EPSG:32643) coordinates to standard WGS84 (EPSG:4326),
and exposes the 151 segments as a GeoJSON FeatureCollection.
"""
from __future__ import annotations

import json
import math
import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import HTTPException
import networkx as nx
import pandas as pd
import pyproj
from shapely import wkt

from src.api.config import settings
from src.api.schemas.auth import UserProfile, UserRole
from src.api.schemas.corridor import (
    AlongRouteServiceItem,
    CorridorGeoJSONResponse,
    GeoJSONGeometry,
    OfficialAdvisoriesResponse,
    SegmentFeature,
    SegmentFeatureDetailResponse,
    SegmentProperties,
    SegmentWeatherDetail,
)


class CorridorService:
    """Provides corridor network geometry and segment metadata."""

    def __init__(
        self,
        graph_path: Path | None = None,
        static_path: Path | None = None,
    ) -> None:
        self.graph_path = graph_path or settings.corridor_graph_path
        self.static_path = static_path or settings.static_segments_path
        self._geojson_cache: Optional[CorridorGeoJSONResponse] = None
        self._transformer = pyproj.Transformer.from_crs("EPSG:32643", "EPSG:4326", always_xy=True)

    def get_corridor_geojson(self) -> CorridorGeoJSONResponse:
        """Loads and returns the 151 highway segments as a GeoJSON FeatureCollection."""
        if self._geojson_cache is not None:
            return self._geojson_cache

        if not self.graph_path.exists():
            raise FileNotFoundError(f"Corridor graph file not found at: {self.graph_path}")
        if not self.static_path.exists():
            raise FileNotFoundError(f"Static segments CSV not found at: {static_path}")

        # 1. Load graph and static features
        G = nx.read_graphml(self.graph_path)
        static_df = pd.read_csv(self.static_path).set_index("segment_id")

        features: List[SegmentFeature] = []

        for u, v, k, data in G.edges(keys=True, data=True):
            segment_id = f"{u}_{v}_{k}"
            stat_row = static_df.loc[segment_id] if segment_id in static_df.index else None

            # 2. Extract and reproject coordinates
            geom_wkt = data.get("geometry")
            coords_wgs84: List[List[float]] = []

            if geom_wkt:
                geom = wkt.loads(geom_wkt)
                for x, y in geom.coords:
                    lon, lat = self._transformer.transform(x, y)
                    coords_wgs84.append([round(lon, 6), round(lat, 6)])
            else:
                # Fallback to straight line between nodes u and v
                u_node = G.nodes[u]
                v_node = G.nodes[v]
                ux, uy = float(u_node["x"]), float(u_node["y"])
                vx, vy = float(v_node["x"]), float(v_node["y"])
                u_lon, u_lat = self._transformer.transform(ux, uy)
                v_lon, v_lat = self._transformer.transform(vx, vy)
                coords_wgs84 = [
                    [round(u_lon, 6), round(u_lat, 6)],
                    [round(v_lon, 6), round(v_lat, 6)],
                ]

            # 3. Build segment properties
            length_m = float(stat_row["length_m"]) if stat_row is not None else float(data.get("length", 0.0))
            slope = float(stat_row["slope"]) if stat_row is not None else float(data.get("slope", 0.0))
            elevation_m = float(stat_row["elevation_m"]) if stat_row is not None else float(data.get("elevation", 0.0))
            highway = str(stat_row["highway"]) if stat_row is not None and "highway" in stat_row else data.get("highway", "trunk")
            ref = str(stat_row["ref"]) if stat_row is not None and "ref" in stat_row else data.get("ref", "NH44")
            is_primary = int(stat_row["is_primary_road"]) if stat_row is not None and "is_primary_road" in stat_row else 1

            props = SegmentProperties(
                segment_id=segment_id,
                length_m=round(length_m, 1),
                slope=round(slope, 4),
                elevation_m=round(elevation_m, 1),
                highway=highway,
                ref=ref,
                is_primary_road=is_primary,
            )

            feature = SegmentFeature(
                type="Feature",
                id=segment_id,
                geometry=GeoJSONGeometry(type="LineString", coordinates=coords_wgs84),
                properties=props,
            )
            features.append(feature)

        self._geojson_cache = CorridorGeoJSONResponse(
            type="FeatureCollection",
            features=features,
            corridor_name="NH-44 Ramban–Banihal Pilot Stretch",
            total_segments=len(features),
            crs="EPSG:4326",
        )
        return self._geojson_cache

    def get_segment_features(
        self,
        segment_id: str,
        date_str: str,
        current_user: Optional[UserProfile] = None,
    ) -> SegmentFeatureDetailResponse:
        """Retrieves real input features (terrain + ERA5-Land weather) and linked reports for a segment."""
        # 1. Fetch static properties
        geojson = self.get_corridor_geojson()
        feat = next((f for f in geojson.features if f.id == segment_id), None)
        if not feat:
            raise HTTPException(status_code=404, detail=f"Corridor segment '{segment_id}' not found.")

        props = feat.properties
        slope_pct = round(props.slope * 100, 2)
        slope_deg = round(math.degrees(math.atan(props.slope)), 2)

        # 2. Query weather from SQLite
        weather_detail = None
        db_conn = sqlite3.connect(settings.db_path)
        db_conn.row_factory = sqlite3.Row
        try:
            w_row = db_conn.execute(
                "SELECT * FROM segment_weather WHERE segment_id = ? AND date = ?",
                (segment_id, date_str),
            ).fetchone()
            if w_row:
                weather_detail = SegmentWeatherDetail(
                    date=date_str,
                    precip_mm=round(float(w_row["precip_mm"]), 2),
                    precip_3d_mm=round(float(w_row["precip_3d_mm"]), 2),
                    precip_7d_mm=round(float(w_row["precip_7d_mm"]), 2),
                    temp_mean_c=round(float(w_row["temp_mean_c"]), 1),
                    temp_min_c=round(float(w_row["temp_min_c"]), 1),
                    snowfall_mm_we=round(float(w_row["snowfall_mm_we"]), 2),
                    snow_depth_m=round(max(0.0, float(w_row["snow_depth_m"])), 4),
                )

            # 3. Linked field reports
            is_patrol = current_user is not None and current_user.role in (UserRole.PATROL.value, UserRole.ADMIN.value)
            if is_patrol:
                rep_rows = db_conn.execute(
                    "SELECT id, category, status, description, created_at, is_simulated FROM reports WHERE nearest_segment_id = ?",
                    (segment_id,),
                ).fetchall()
            else:
                rep_rows = db_conn.execute(
                    "SELECT id, category, status, description, created_at, is_simulated FROM reports WHERE nearest_segment_id = ? AND status IN ('verified', 'assigned')",
                    (segment_id,),
                ).fetchall()

            reports = [dict(r) for r in rep_rows]
        finally:
            db_conn.close()

        return SegmentFeatureDetailResponse(
            segment_id=segment_id,
            date=date_str,
            length_m=props.length_m,
            slope_deg=slope_deg,
            slope_pct=slope_pct,
            elevation_m=props.elevation_m,
            highway=props.highway,
            weather=weather_detail,
            reports=reports,
        )

    def get_along_route_services(self) -> List[AlongRouteServiceItem]:
        """Loads verified along-route facilities from static data file."""
        services_path = Path("data/along_route_services.json")
        if not services_path.exists():
            return []
        with open(services_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            return [AlongRouteServiceItem(**item) for item in data]

    def get_official_advisories(self) -> OfficialAdvisoriesResponse:
        """Loads official J&K Traffic Police channels and contacts."""
        adv_path = Path("data/official_advisories.json")
        if not adv_path.exists():
            raise HTTPException(status_code=404, detail="Advisories configuration not found.")
        with open(adv_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            return OfficialAdvisoriesResponse(**data)

    def get_corridor_weather(self, date_str: str) -> Dict[str, Any]:
        """Returns corridor-wide weather snapshot across all segments for a date."""
        db_conn = sqlite3.connect(settings.db_path)
        db_conn.row_factory = sqlite3.Row
        try:
            rows = db_conn.execute(
                "SELECT segment_id, precip_mm, precip_7d_mm, temp_mean_c FROM segment_weather WHERE date = ?",
                (date_str,),
            ).fetchall()
        finally:
            db_conn.close()

        if not rows:
            raise HTTPException(status_code=404, detail=f"No weather observations stored for date '{date_str}'.")

        precips = [float(r["precip_mm"]) for r in rows]
        temps = [float(r["temp_mean_c"]) for r in rows]

        return {
            "date": date_str,
            "data_source": "ERA5-Land daily reanalysis (Historical Retrospective)",
            "total_segments_covered": len(rows),
            "max_precipitation_mm": round(max(precips), 2),
            "mean_precipitation_mm": round(sum(precips) / len(precips), 2),
            "mean_temperature_c": round(sum(temps) / len(temps), 1),
            "segments": {r["segment_id"]: {"precip_mm": round(float(r["precip_mm"]), 2), "temp_mean_c": round(float(r["temp_mean_c"]), 1)} for r in rows},
        }


corridor_service = CorridorService()

