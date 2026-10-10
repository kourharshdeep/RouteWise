"""
Week 1: GIS Data Acquisition & NH-44 Corridor Modeling
--------------------------------------------------------
1. Pull a pilot sub-corridor of NH-44 from OpenStreetMap
2. Download SRTM elevation for the same bounding box (OpenTopography API)
3. Attach slope/elevation to every road segment (edge)
4. Export a graph file that Weeks 2 and 5 (ST-GNN) will reuse

Install first:
    pip install osmnx rasterio networkx geopandas requests python-dotenv

API key: put it in a file named .env in this folder (never hardcode it):
    OPENTOPO_API_KEY=your-key-here
"""
import os
import osmnx as ox
import requests
import rasterio
import numpy as np
import networkx as nx
from dotenv import load_dotenv

load_dotenv()  # reads the .env file in this folder

# ---------------------------------------------------------------
# STEP 0: Define your pilot corridor as a bounding box.
# Don't model all of NH-44 — pick one genuinely high-risk stretch,
# e.g. the Ramban–Banihal section (landslide-prone). Get the coords
# from Google Maps: right-click each end point -> copy lat/lon.
# ---------------------------------------------------------------
NORTH, SOUTH, EAST, WEST = 33.475, 33.211, 75.262, 75.161
DEM_PATH = "corridor_dem.tif"

# ---------------------------------------------------------------
# STEP 1: Pull the road graph for just that box
# ---------------------------------------------------------------
G = ox.graph_from_bbox(
    bbox=(WEST, SOUTH, EAST, NORTH),
    network_type="drive",
)
# OSMnx v2 already simplifies the graph, so no simplify_graph() call here.
G = ox.project_graph(G)  # projects to metric CRS (meters)

print(f"Graph pulled: {len(G.nodes)} nodes, {len(G.edges)} edges")

# ---------------------------------------------------------------
# STEP 2: Download SRTM DEM covering the same box
# (only downloads if the file doesn't already exist)
# ---------------------------------------------------------------
if not os.path.exists(DEM_PATH):
    OPENTOPO_API_KEY = os.getenv("OPENTOPO_API_KEY")
    if not OPENTOPO_API_KEY:
        raise SystemExit(
            "OPENTOPO_API_KEY not found. Create a .env file in this folder "
            "containing:  OPENTOPO_API_KEY=your-key-here"
        )

    response = requests.get(
        "https://portal.opentopography.org/API/globaldem",
        params={
            "demtype": "SRTMGL1",
            "south": SOUTH,
            "north": NORTH,
            "west": WEST,
            "east": EAST,
            "outputFormat": "GTiff",
            "API_Key": OPENTOPO_API_KEY,
        },
    )
    response.raise_for_status()
    with open(DEM_PATH, "wb") as f:
        f.write(response.content)
    print(f"Downloaded DEM to {DEM_PATH}")
else:
    print(f"Using existing DEM: {DEM_PATH}")

# ---------------------------------------------------------------
# STEP 3: Sample elevation for every node, compute per-edge slope
# ---------------------------------------------------------------
with rasterio.open(DEM_PATH) as dem:
    elevation_band = dem.read(1)  # read the raster once, not per node

    def elevation_at(lon, lat):
        row, col = dem.index(lon, lat)
        return float(elevation_band[row, col])

    # un-project node coords back to lat/lon just for DEM lookup
    G_latlon = ox.project_graph(G, to_crs="EPSG:4326")
    for node, data in G_latlon.nodes(data=True):
        G.nodes[node]["elevation"] = elevation_at(data["x"], data["y"])

for u, v, k, data in G.edges(keys=True, data=True):
    elev_u = G.nodes[u]["elevation"]
    elev_v = G.nodes[v]["elevation"]
    length = data.get("length", 1)  # meters, added automatically by OSMnx
    data["elevation_gain"] = abs(elev_v - elev_u)
    data["slope"] = min(data["elevation_gain"] / max(length, 1), 0.3)  # rise/run
    data["road_type"] = data.get("highway", "unclassified")

# ---------------------------------------------------------------
# STEP 4: Export — this file is what Week 2/5 will load and extend
# ---------------------------------------------------------------
ox.save_graphml(G, filepath="nh44_corridor_graph.graphml")
print("Saved nh44_corridor_graph.graphml — this is your Week 1 deliverable.")

# ---------------------------------------------------------------
# STEP 5 (evidence for your PPT/demo): quick visual check
# ---------------------------------------------------------------
fig, ax = ox.plot_graph(
    G, node_color="red", edge_color="gray", show=False, close=False
)
fig.savefig("week1_corridor_map.png", dpi=200)
print("Saved week1_corridor_map.png as demo evidence.")