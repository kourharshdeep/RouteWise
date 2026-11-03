"""Spatial Clustering of NH-44 Corridor Road Segments.

ERA5-Land reanalysis has a native spatial resolution of ~0.1° (~9 km).
To minimize external API calls and respect rate limits, the 151 corridor segments
are grouped by nearest 0.1° grid centroid. Each unique atmospheric grid cell is
queried once, and observations are fanned out to all constituent segments.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Tuple

from src.services.corridor_service import corridor_service


@dataclass(frozen=True)
class GridCluster:
    cluster_id: str
    latitude: float
    longitude: float
    segment_ids: Tuple[str, ...]


def build_corridor_grid_clusters(grid_resolution: float = 0.1) -> List[GridCluster]:
    """Groups all 151 segments into ~9km grid clusters based on segment midpoints."""
    geojson = corridor_service.get_corridor_geojson()
    cluster_map: Dict[Tuple[float, float], List[str]] = {}

    for feat in geojson.features:
        coords = feat.geometry.coordinates
        if not coords:
            continue
        # Compute midpoint of segment line coordinates [lon, lat]
        mid_lon = sum(pt[0] for pt in coords) / len(coords)
        mid_lat = sum(pt[1] for pt in coords) / len(coords)

        # Round to nearest grid resolution (0.1 deg ~ 9-11 km)
        c_lat = round(round(mid_lat / grid_resolution) * grid_resolution, 4)
        c_lon = round(round(mid_lon / grid_resolution) * grid_resolution, 4)

        key = (c_lat, c_lon)
        if key not in cluster_map:
            cluster_map[key] = []
        cluster_map[key].append(feat.id)

    clusters: List[GridCluster] = []
    for idx, ((lat, lon), seg_ids) in enumerate(sorted(cluster_map.items())):
        cluster_id = f"cell_{idx}_{lat}_{lon}"
        clusters.append(
            GridCluster(
                cluster_id=cluster_id,
                latitude=lat,
                longitude=lon,
                segment_ids=tuple(sorted(seg_ids)),
            )
        )

    return clusters
