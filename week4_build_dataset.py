"""
Phase 4A: Build the training tables for the ST-GNN
----------------------------------------------------
Inputs  : nh44_corridor_graph.graphml            (Week 1)
          data/weather_daily_by_segment.csv       (Week 2B)
          data/labelled_events.csv                (Week 2C, from week2c_disruption_log.py)
Outputs : data/segment_static.csv      one row per road segment (slope, elevation, length, road class)
          data/segment_adjacency.csv   which segments touch each other (the graph edges for the GNN)
          data/training_samples.csv    labelled segment-days with a time-based split

Run (venv active):  python week4_build_dataset.py

Design choices (be ready to explain these in your viva):
  * Unit of prediction = one road segment on one day. label = 1 if a REAL, sourced
    disruption was logged on that segment that day, else 0.
  * Only events inside the weather window (2021-2025) can be used.
  * Time-based split, never random: train 2021-2022, validation 2023, test 2024-2025.
  * Real disruptions are rare, so negatives are SAMPLED: every positive is kept, and
    about 30 negatives per positive are drawn. Half are random days, half are wet days
    (top 10% of 7-day rainfall) so the model must learn more than "rain = risk".
    Because of this sampling, predicted probabilities are relative risk scores, not
    true daily probabilities. Say this in the report.
  * Negatives within 3 days of a logged event on the same segment are dropped (the
    log is incomplete, so those days are uncertain).
  * Weather features for day D use only information up to day D.
"""
import os

import networkx as nx
import numpy as np
import osmnx as ox
import pandas as pd

GRAPH_PATH = "nh44_corridor_graph.graphml"
WEATHER_CSV = "data/weather_daily_by_segment.csv"
EVENTS_CSV = "data/labelled_events.csv"

TRAIN_END = "2022-12-31"
VAL_END = "2023-12-31"
NEG_PER_POS = 30
WET_QUANTILE = 0.90
EXCLUDE_DAYS = 3
SEED = 42


def first(v):
    return v[0] if isinstance(v, list) else v


def build_static(G):
    rows = []
    for u, v, k, d in G.edges(keys=True, data=True):
        eu, ev = G.nodes[u].get("elevation"), G.nodes[v].get("elevation")
        elev = np.nanmean([float(eu), float(ev)]) if eu is not None and ev is not None else np.nan
        rows.append({
            "segment_id": f"{u}_{v}_{k}",
            "u": u, "v": v,
            "length_m": float(d.get("length", np.nan)),
            "slope": float(d.get("slope", np.nan)),
            "elevation_m": elev,
            "highway": str(first(d.get("highway", ""))),
            "ref": str(d.get("ref", "")),
        })
    df = pd.DataFrame(rows)
    df["is_primary_road"] = df["highway"].isin(["trunk", "primary", "trunk_link", "primary_link"]).astype(int)
    for c in ("length_m", "slope", "elevation_m"):
        df[c] = df[c].fillna(df[c].median())
    return df


def build_adjacency(static):
    """Two segments are neighbours if they share an end node (line graph of the road graph)."""
    node_to_seg = {}
    for sid, u, v in zip(static["segment_id"], static["u"], static["v"]):
        node_to_seg.setdefault(u, []).append(sid)
        node_to_seg.setdefault(v, []).append(sid)
    pairs = set()
    for segs in node_to_seg.values():
        for a in segs:
            for b in segs:
                if a != b:
                    pairs.add((a, b))
    return pd.DataFrame(sorted(pairs), columns=["src", "dst"])


def assign_split(dates):
    d = pd.to_datetime(dates)
    return np.where(d <= TRAIN_END, "train", np.where(d <= VAL_END, "val", "test"))


def main():
    for p in (GRAPH_PATH, WEATHER_CSV, EVENTS_CSV):
        if not os.path.exists(p):
            raise SystemExit(f"Missing {p}. Finish the earlier weeks first.")

    G = ox.load_graphml(GRAPH_PATH)
    static = build_static(G)
    adj = build_adjacency(static)
    static.drop(columns=["u", "v"]).to_csv("data/segment_static.csv", index=False)
    adj.to_csv("data/segment_adjacency.csv", index=False)
    print(f"Segments: {len(static)}   graph links between segments: {len(adj)}")

    weather = pd.read_csv(WEATHER_CSV, usecols=["segment_id", "date", "precip_7d_mm", "precip_mm"])
    w_start, w_end = weather["date"].min(), weather["date"].max()
    print(f"Weather window: {w_start} to {w_end}")

    ev = pd.read_csv(EVENTS_CSV)
    ev = ev[(ev["date"] >= w_start) & (ev["date"] <= w_end)]
    ev = ev[ev["segment_id"].isin(set(weather["segment_id"]))]
    pos = ev[["segment_id", "date"]].drop_duplicates().assign(label=1, neg_kind="positive")
    print(f"Usable positive segment-days inside the weather window: {len(pos)}")
    if pos.empty:
        raise SystemExit("No usable events in the weather window.")

    # Candidate negatives: every segment-day without an event or an event within +-3 days
    panel = weather[["segment_id", "date", "precip_7d_mm"]].copy()
    panel["d"] = pd.to_datetime(panel["date"])
    blocked = set()
    for sid, d in zip(pos["segment_id"], pd.to_datetime(pos["date"])):
        for off in range(-EXCLUDE_DAYS, EXCLUDE_DAYS + 1):
            blocked.add((sid, (d + pd.Timedelta(days=off)).strftime("%Y-%m-%d")))
    keys = list(zip(panel["segment_id"], panel["date"]))
    panel = panel[[k not in blocked for k in keys]]

    rng = np.random.default_rng(SEED)
    rows = [pos]
    wet_cut = panel["precip_7d_mm"].quantile(WET_QUANTILE)
    for split in ("train", "val", "test"):
        n_pos = int((assign_split(pos["date"]) == split).sum())
        if n_pos == 0:
            print(f"  WARNING: no positives in {split}; sampling a small set of negatives only")
        n_neg = max(n_pos, 3) * NEG_PER_POS
        pool = panel[assign_split(panel["date"]) == split]
        wet = pool[pool["precip_7d_mm"] >= wet_cut]
        rnd = pool.sample(min(n_neg // 2, len(pool)), random_state=SEED)
        wet = wet.sample(min(n_neg - len(rnd), len(wet)), random_state=SEED)
        rows.append(rnd[["segment_id", "date"]].assign(label=0, neg_kind="random"))
        rows.append(wet[["segment_id", "date"]].assign(label=0, neg_kind="wet_day"))

    out = pd.concat(rows, ignore_index=True).drop_duplicates(["segment_id", "date"])
    out["split"] = assign_split(out["date"])
    out["is_simulated"] = 0  # keep at 0: no invented data in this table
    out = out.sort_values(["date", "segment_id"]).reset_index(drop=True)
    out.to_csv("data/training_samples.csv", index=False)

    print("\nSamples per split (label counts):")
    print(out.groupby(["split", "label"]).size().unstack(fill_value=0))
    print("\nSaved data/segment_static.csv, data/segment_adjacency.csv, data/training_samples.csv")
    small = out[out["label"] == 1].groupby("split").size()
    if (small.reindex(["train", "val", "test"]).fillna(0) < 3).any():
        print("\nWARNING: a split has fewer than 3 real events, so its scores will be unreliable.")
        print("More real, sourced events (especially 2024 and winter snow) is the best way to improve this.")
    print("Next: upload these 3 files + data/weather_daily_by_segment.csv to Google Drive for Colab.")


if __name__ == "__main__":
    main()