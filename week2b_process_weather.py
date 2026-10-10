"""
Week 2B: Turn the raw ERA5-Land files into a daily weather table per road segment
-----------------------------------------------------------------------------------
Input : data/weather/*.nc (from week2a)  +  nh44_corridor_graph.graphml (Week 1)
Output: data/weather_daily_by_segment.csv
        columns: segment_id, date, precip_mm, snowfall_mm_we, temp_mean_c,
                 temp_min_c, snow_depth_m, precip_3d_mm, precip_7d_mm

Run:  python week2b_process_weather.py

Key facts handled here:
  * ERA5-Land precipitation/snowfall are ACCUMULATED from 00:00 UTC. The value
    stamped 00:00 on day D+1 is the total for day D. So daily total for day D
    is read from the 00:00 reading of the NEXT day.
  * Units: precipitation/snowfall in metres of water -> converted to mm.
    Temperature in Kelvin -> Celsius. Snow depth (sde) is physical snow depth in metres.
  * Each road segment gets the weather of the nearest ERA5-Land grid cell
    (about 9 km resolution; fine for a corridor-level pilot, but it means
    neighbouring segments often share the same weather. State this limitation).
"""
import glob
import os

import numpy as np
import osmnx as ox
import pandas as pd
import xarray as xr

GRAPH_PATH = "nh44_corridor_graph.graphml"
WEATHER_GLOB = "data/weather/**/*.nc"
OUT_CSV = "data/weather_daily_by_segment.csv"


def load_weather():
    files = sorted(glob.glob(WEATHER_GLOB, recursive=True))
    if not files:
        raise SystemExit("No .nc files found under data/weather/. Run week2a first.")
    datasets = []
    for f in files:
        ds = xr.open_dataset(f)
        # Normalise names across CDS versions
        if "valid_time" in ds.coords or "valid_time" in ds.dims:
            ds = ds.rename({"valid_time": "time"})
        ds = ds.drop_vars(["number", "expver"], errors="ignore")
        datasets.append(ds)
    # Stack the years along time; if one year was split into several files
    # (different variables, same times) they are merged together instead.
    # NOTE: do not use xr.merge(compat="override") here. It keeps only the
    # first file's values and leaves every other year empty.
    combined = xr.combine_by_coords(datasets, combine_attrs="override")
    combined = combined.sortby("time")
    n_days = len(np.unique(combined["time"].dt.floor("D").values))
    print(f"Loaded {len(files)} file(s) covering {n_days} days")
    return combined


def to_grid_daily(ds):
    """Return a DataFrame: one row per (lat, lon, date)."""
    df = ds.to_dataframe().reset_index()
    df["time"] = pd.to_datetime(df["time"])
    df["date"] = df["time"].dt.normalize()

    parts = []
    # --- accumulated variables: use the 00:00 reading, shifted back one day
    acc_cols = [c for c in ("tp", "sf") if c in df.columns]
    if acc_cols:
        midnight = df[df["time"].dt.hour == 0][["latitude", "longitude", "date"] + acc_cols].copy()
        midnight["date"] = midnight["date"] - pd.Timedelta(days=1)
        for c in acc_cols:
            midnight[c] = midnight[c] * 1000.0  # m -> mm
        midnight = midnight.rename(columns={"tp": "precip_mm", "sf": "snowfall_mm_we"})
        parts.append(midnight)

    # --- instantaneous variables: daily statistics of the 4 readings
    grp = df.groupby(["latitude", "longitude", "date"])
    inst = pd.DataFrame(index=grp.size().index)
    if "t2m" in df.columns:
        inst["temp_mean_c"] = grp["t2m"].mean() - 273.15
        inst["temp_min_c"] = grp["t2m"].min() - 273.15
    if "sde" in df.columns:
        inst["snow_depth_m"] = grp["sde"].max()
    parts.append(inst.reset_index())

    out = parts[0]
    for p in parts[1:]:
        out = out.merge(p, on=["latitude", "longitude", "date"], how="outer")
    out = out.sort_values(["latitude", "longitude", "date"])

    # Rolling rainfall: recent rain is what triggers landslides, not just today's
    out["precip_3d_mm"] = (
        out.groupby(["latitude", "longitude"])["precip_mm"]
        .transform(lambda s: s.rolling(3, min_periods=1).sum())
    )
    out["precip_7d_mm"] = (
        out.groupby(["latitude", "longitude"])["precip_mm"]
        .transform(lambda s: s.rolling(7, min_periods=1).sum())
    )
    return out


def segment_to_cell(grid_cells):
    """Map every graph edge to the nearest ERA5-Land grid cell."""
    G = ox.load_graphml(GRAPH_PATH)
    G = ox.project_graph(G, to_crs="EPSG:4326")  # node x/y become lon/lat
    rows = []
    for u, v, k in G.edges(keys=True):
        lon = (G.nodes[u]["x"] + G.nodes[v]["x"]) / 2
        lat = (G.nodes[u]["y"] + G.nodes[v]["y"]) / 2
        d = (grid_cells["latitude"] - lat) ** 2 + (grid_cells["longitude"] - lon) ** 2
        best = grid_cells.loc[d.idxmin()]
        rows.append(
            {
                "segment_id": f"{u}_{v}_{k}",
                "latitude": best["latitude"],
                "longitude": best["longitude"],
            }
        )
    return pd.DataFrame(rows)


def main():
    os.makedirs("data", exist_ok=True)
    ds = load_weather()
    print("Variables found:", list(ds.data_vars))
    grid_daily = to_grid_daily(ds)

    cells = grid_daily[["latitude", "longitude"]].drop_duplicates().reset_index(drop=True)
    print(f"{len(cells)} grid cells cover the corridor")
    seg_map = segment_to_cell(cells)

    merged = seg_map.merge(grid_daily, on=["latitude", "longitude"], how="left")
    merged = merged.drop(columns=["latitude", "longitude"])
    merged["date"] = merged["date"].dt.strftime("%Y-%m-%d")
    merged.to_csv(OUT_CSV, index=False)

    print(f"Saved {OUT_CSV}: {len(merged):,} rows, {merged['segment_id'].nunique()} segments")
    per_year = (
        merged.assign(year=merged["date"].str[:4])
        .groupby("year")["precip_mm"]
        .agg(rows="size", with_data="count")
    )
    print("\nCoverage per year (with_data should be close to rows):")
    print(per_year)
    if (per_year["with_data"] < 0.9 * per_year["rows"]).any():
        print("WARNING: some years are mostly empty. Do not use this table yet.")
    print(merged.describe().T[["count", "mean", "min", "max"]])
    print("\nSanity checks you should do by eye:")
    print(" - precip_mm max should be tens of mm, not thousands or 0.0 everywhere")
    print(" - temp_mean_c should be roughly -10 to 35 over the year")
    print(" - the last date of each year has no precip (needs 1 Jan of next year)")


if __name__ == "__main__":
    main()