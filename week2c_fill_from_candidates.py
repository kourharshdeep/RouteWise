"""
Week 2C helper: fill data/disruption_log.csv from data/disruption_candidates.csv
------------------------------------------------------------------------------------
data/disruption_candidates.csv holds REAL reported events (each with a source URL).
This script looks up coordinates for the place names (OpenStreetMap Nominatim via
OSMnx), keeps only results that fall inside your Week 1 corridor, and merges the
rows into data/disruption_log.csv without touching rows you already added.

Run (venv active, internet on):
    python week2c_fill_from_candidates.py

Then:
    python week2c_disruption_log.py

IMPORTANT, be honest about what this does:
  * Coordinates come from place-name lookup, so they are APPROXIMATE (village centre,
    not the exact slide). Every such row is marked location_confidence = low.
  * Places OSM does not know (for example "Cafeteria Morh") use the fallback place
    in the CSV, or end up in data/needs_manual_coordinates.csv for you to look up
    on Google Maps and type in.
  * Rows whose notes start with "CHECK DATE" were inferred from an article's
    "Saturday"/"Tuesday" wording. Open the link and confirm the date before training.
"""
import os
import time

import osmnx as ox
import pandas as pd

CANDIDATES = "data/disruption_candidates.csv"
LOG_PATH = "data/disruption_log.csv"
MANUAL_PATH = "data/needs_manual_coordinates.csv"
REPORT_PATH = "data/geocode_report.csv"

# Week 1 corridor box plus a margin
NORTH, SOUTH, EAST, WEST = 33.475, 33.211, 75.262, 75.161
MARGIN = 0.05

LOG_COLUMNS = [
    "date", "location_desc", "lat", "lon", "location_confidence", "disruption_type",
    "closure", "duration_hours", "source_name", "source_url", "notes",
]


def inside_corridor(lat, lon):
    return (SOUTH - MARGIN <= lat <= NORTH + MARGIN) and (WEST - MARGIN <= lon <= EAST + MARGIN)


def lookup(query):
    """Return (lat, lon) or None. Nominatim allows about 1 request per second."""
    if not isinstance(query, str) or not query.strip():
        return None
    try:
        time.sleep(1.1)
        lat, lon = ox.geocode(query)
        return float(lat), float(lon)
    except Exception:
        return None


def main():
    if not os.path.exists(CANDIDATES):
        raise SystemExit(f"{CANDIDATES} not found. Put the candidates file in the data folder.")
    cand = pd.read_csv(CANDIDATES)
    ox.settings.requests_timeout = 60

    cache = {}
    new_rows, report, manual = [], [], []

    for _, r in cand.iterrows():
        got, used = None, ""
        for label, query in (("primary", r["geocode_query"]), ("fallback", r["fallback_query"])):
            if query in cache:
                res = cache[query]
            else:
                res = lookup(query)
                cache[query] = res
            if res and inside_corridor(*res):
                got, used = res, f"{label}: {query}"
                break
            if res:
                report.append({"location_desc": r["location_desc"], "query": query,
                               "result": f"{res[0]:.4f},{res[1]:.4f}", "status": "outside corridor, rejected"})
        row = {
            "date": r["date"], "location_desc": r["location_desc"],
            "lat": "", "lon": "", "location_confidence": "low",
            "disruption_type": r["disruption_type"], "closure": r["closure"],
            "duration_hours": r["duration_hours"] if pd.notna(r["duration_hours"]) else "",
            "source_name": r["source_name"], "source_url": r["source_url"],
            "notes": r["notes"] if pd.notna(r["notes"]) else "",
        }
        if got:
            row["lat"], row["lon"] = round(got[0], 5), round(got[1], 5)
            row["notes"] = (row["notes"] + "; " if row["notes"] else "") + "coordinates approximate (place-name lookup)"
            new_rows.append(row)
            report.append({"location_desc": r["location_desc"], "query": used,
                           "result": f"{got[0]:.4f},{got[1]:.4f}", "status": "ok"})
        else:
            manual.append(row)
            report.append({"location_desc": r["location_desc"], "query": "",
                           "result": "", "status": "NOT FOUND, add coordinates by hand"})

    pd.DataFrame(report).to_csv(REPORT_PATH, index=False)

    # Merge with the existing log (keep the user's own rows, skip duplicates)
    if os.path.exists(LOG_PATH):
        log = pd.read_csv(LOG_PATH)
        log = log[log["location_desc"] != "EXAMPLE_DELETE_ME"]
    else:
        log = pd.DataFrame(columns=LOG_COLUMNS)
    key = lambda d: (str(d["date"]), str(d["location_desc"]), str(d["source_url"]))
    have = {key(x) for _, x in log.iterrows()}
    fresh = [r for r in new_rows if key(r) not in have]
    merged = pd.concat([log, pd.DataFrame(fresh, columns=LOG_COLUMNS)], ignore_index=True)
    merged = merged.sort_values("date").reset_index(drop=True)
    merged.to_csv(LOG_PATH, index=False)

    if manual:
        pd.DataFrame(manual, columns=LOG_COLUMNS).to_csv(MANUAL_PATH, index=False)

    print(f"Added {len(fresh)} rows to {LOG_PATH} ({len(new_rows) - len(fresh)} already present).")
    print(f"{len(manual)} rows need coordinates by hand -> {MANUAL_PATH}" if manual
          else "Every row got coordinates.")
    print(f"Lookup details -> {REPORT_PATH}")
    print("\nNext: python week2c_disruption_log.py   (snaps events to road segments, makes data/events_map.png)")


if __name__ == "__main__":
    main()