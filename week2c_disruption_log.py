"""
Week 2C: snap disruption events to road segments and map them
--------------------------------------------------------------
Reads  data/disruption_log.csv  (filled by week2c_fill_from_candidates.py)
Reads  nh44_corridor_graph.graphml  (Week 1)
Writes data/disruption_log_snapped.csv  (every event + segment_id, snap_dist_m, snap_ok)
Writes data/labelled_events.csv         (only events usable as labels; read by Week 4)
Writes data/events_map.png

segment_id uses the same format as Week 4 and the weather file: "<u>_<v>_<k>".

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
WEATHER_CSV = "data/weather_daily_by_segment.csv"
OUT_CSV = "data/disruption_log_snapped.csv"
OUT_LABELLED = "data/labelled_events.csv"
OUT_MAP = "data/events_map.png"

# Week 1 corridor box
NORTH, SOUTH, EAST, WEST = 33.475, 33.211, 75.262, 75.161
MAX_SNAP_M = 1500  # events farther than this from any road are not used as labels

for p in (GRAPH_PATH, LOG_PATH):
    if not os.path.exists(p):
        raise SystemExit(f"{p} not found. Run this from the RouteWise folder.")

G = ox.load_graphml(GRAPH_PATH)  # already projected (meters) from Week 1
log = pd.read_csv(LOG_PATH)
log = log[log["location_desc"] != "EXAMPLE_DELETE_ME"]

# ---- clean lat/lon: skip rows where they are blank or not numbers ----
raw = log[["lat", "lon"]].copy()
log["lat"] = pd.to_numeric(log["lat"], errors="coerce")
log["lon"] = pd.to_numeric(log["lon"], errors="coerce")
bad = log["lat"].isna() | log["lon"].isna()
if bad.any():
    print(f"\n{bad.sum()} rows skipped, lat/lon missing or not a number (CSV line = row number + 2):")
    out = log.loc[bad, ["date", "location_desc"]].copy()
    out["raw_lat"], out["raw_lon"] = raw.loc[bad, "lat"], raw.loc[bad, "lon"]
    print(out.to_string())
log = log[~bad].reset_index(drop=True)

# ---- clean dates: Week 4 needs YYYY-MM-DD ----
dates = pd.to_datetime(log["date"], errors="coerce")
bad_date = dates.isna()
if bad_date.any():
    print(f"\n{bad_date.sum()} rows skipped, date is not a valid date:")
    print(log.loc[bad_date, ["date", "location_desc"]].to_string())
log["date"] = dates.dt.strftime("%Y-%m-%d")
log = log[~bad_date].reset_index(drop=True)

# ---- warn about points outside the corridor (typo or swapped lat/lon) ----
outside = log[~log["lat"].between(SOUTH - 0.05, NORTH + 0.05) | ~log["lon"].between(WEST - 0.05, EAST + 0.05)]
if len(outside):
    print(f"\n{len(outside)} events are outside the corridor box, check lat/lon (maybe swapped or mistyped):")
    print(outside[["date", "location_desc", "lat", "lon"]].to_string())

print(f"\n{len(log)} events with coordinates")

# lat/lon -> the graph's projected CRS
pts = gpd.GeoSeries(gpd.points_from_xy(log["lon"], log["lat"]), crs="EPSG:4326").to_crs(G.graph["crs"])

edges, dists = ox.distance.nearest_edges(G, pts.x.values, pts.y.values, return_dist=True)
log["segment_id"] = [f"{u}_{v}_{k}" for u, v, k in edges]
log["snap_dist_m"] = [round(float(d), 1) for d in dists]
log["snap_ok"] = log["snap_dist_m"] <= MAX_SNAP_M
log.to_csv(OUT_CSV, index=False)

# ---- labels for Week 4: only events that snapped to a nearby road ----
labelled = log[log["snap_ok"]].copy()
cols = ["date", "segment_id", "location_desc", "disruption_type", "closure",
        "location_confidence", "snap_dist_m", "source_url"]
labelled[[c for c in cols if c in labelled.columns]].to_csv(OUT_LABELLED, index=False)

# ---- checks ----
print(f"\nEvents landed on {log['segment_id'].nunique()} different road segments:")
print(log["segment_id"].value_counts().head(10).to_string())
print(f"\nSnap distance (m): median {log['snap_dist_m'].median():.0f}, max {log['snap_dist_m'].max():.0f}")
far = log[~log["snap_ok"]]
if len(far):
    print(f"\n{len(far)} events are more than {MAX_SNAP_M/1000:.1f} km from any road, left out of labelled_events.csv:")
    print(far[["date", "location_desc", "lat", "lon", "snap_dist_m"]].to_string(index=False))

print(f"\nlabelled_events.csv: {len(labelled)} events, by year:")
print(pd.to_datetime(labelled["date"]).dt.year.value_counts().sort_index().to_string())
print("(Week 4 can only use events inside the weather window, 2021 to 2025.)")

# check the IDs match the weather file
if os.path.exists(WEATHER_CSV):
    try:
        w_ids = set(pd.read_csv(WEATHER_CSV, usecols=["segment_id"])["segment_id"].astype(str).unique())
        hit = labelled["segment_id"].isin(w_ids).sum()
        print(f"\nSegment IDs found in {WEATHER_CSV}: {hit} of {len(labelled)} labelled events")
        if hit == 0:
            print("WARNING: none match. Compare a segment_id from the weather file with these:")
            print("  weather:", sorted(w_ids)[:2], " events:", labelled["segment_id"].head(2).tolist())
    except Exception as e:
        print(f"\n(Could not check IDs against the weather file: {e})")

print(f"\nSaved {OUT_CSV}\nSaved {OUT_LABELLED}")

# ---- map ----
fig, ax = ox.plot_graph(G, node_size=0, edge_color="gray", show=False, close=False)
ax.scatter(pts.x, pts.y, c="red", s=30, zorder=5, label="disruption events")
ax.legend(loc="upper right")
fig.savefig(OUT_MAP, dpi=200)
print(f"Saved {OUT_MAP}")