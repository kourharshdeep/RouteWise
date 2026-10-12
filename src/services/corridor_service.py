"""Corridor road network topology and GeoJSON service.

Parses the OpenStreetMap corridor graph from nh44_corridor_graph.graphml,
reprojects projected UTM 43N (EPSG:32643) coordinates to standard WGS84 (EPSG:4326),
and exposes the 151 segments as a GeoJSON FeatureCollection.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

import networkx as nx
import pandas as pd
import pyproj
from shapely import wkt

from src.api.config import settings
from src.api.schemas.corridor import (
    CorridorGeoJSONResponse,
    GeoJSONGeometry,
    SegmentFeature,
    SegmentProperties,
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


corridor_service = CorridorService()
