"""
Week 2C: snap disruption events to road segments and map them
--------------------------------------------------------------
Reads  data/disruption_log.csv  (filled by week2c_fill_from_candidates.py)
Reads  nh44_corridor_graph.graphml  (Week 1)
Writes data/disruption_log_snapped.csv  (adds edge_id and snap_dist_m)
Writes data/events_map.png

Run from the RouteWise folder:
    python week2c_disruption_log.py
"""
import os

import geopandas as gpd
import matplotlib.pyplot as plt
import osmnx as ox
import pandas as pd

GRAPH_PATH = "nh44_corridor_graph.graphml"
LOG_PATH = "data/disruption_log.csv"
OUT_CSV = "data/disruption_log_snapped.csv"
OUT_MAP = "data/events_map.png"

for p in (GRAPH_PATH, LOG_PATH):
    if not os.path.exists(p):
        raise SystemExit(f"{p} not found. Run this from the RouteWise folder.")

G = ox.load_graphml(GRAPH_PATH)  # already projected (meters) from Week 1
log = pd.read_csv(LOG_PATH)
log = log[log["location_desc"] != "EXAMPLE_DELETE_ME"]
log = log.dropna(subset=["lat", "lon"]).reset_index(drop=True)
print(f"{len(log)} events with coordinates")

# lat/lon -> the graph's projected CRS
pts = gpd.GeoSeries(gpd.points_from_xy(log["lon"], log["lat"]), crs="EPSG:4326").to_crs(G.graph["crs"])

edges, dists = ox.distance.nearest_edges(G, pts.x.values, pts.y.values, return_dist=True)
log["edge_id"] = [f"{u}-{v}-{k}" for u, v, k in edges]
log["snap_dist_m"] = [round(float(d), 1) for d in dists]
log.to_csv(OUT_CSV, index=False)

# ---- checks ----
print(f"\nEvents landed on {log['edge_id'].nunique()} different road segments:")
print(log["edge_id"].value_counts().head(10).to_string())
print(f"\nSnap distance (m): median {log['snap_dist_m'].median():.0f}, max {log['snap_dist_m'].max():.0f}")
far = log[log["snap_dist_m"] > 1500]
if len(far):
    print(f"\n{len(far)} events are more than 1.5 km from any road, check their coordinates:")
    print(far[["date", "location_desc", "lat", "lon", "snap_dist_m"]].to_string(index=False))
print(f"\nSaved {OUT_CSV}")

# ---- map ----
fig, ax = ox.plot_graph(G, node_size=0, edge_color="gray", show=False, close=False)
ax.scatter(pts.x, pts.y, c="red", s=30, zorder=5, label="disruption events")
ax.legend(loc="upper right")
fig.savefig(OUT_MAP, dpi=200)
print(f"Saved {OUT_MAP}")