# RouteWise

Predictive, offline-first route safety for **NH-44 in Jammu & Kashmir**.
RouteWise models landslide, snow and shooting-stone disruption risk for each road segment of the highway, so that routes can later be chosen on predicted safety and not just distance. It is a minor project (Group 21, MIET Jalandhar).

**Pilot corridor:** Ramban to Banihal (latitude 33.211 to 33.475, longitude 75.161 to 75.262), a landslide-prone stretch of the Jammu-Srinagar highway.

**Status:** work in progress. Weeks 1 to 3 of the project timeline are done, plus the dataset preparation for the model. The ST-GNN model is next.

## Project plan and progress

| Timeline week | Topic | Status |
|---|---|---|
| 1 | GIS data and NH-44 graph | Done |
| 2 | Weather and historical disruption data | Done |
| 3 | Offline-first SQLite schema | Done |
| Prep | Dataset for the model (feeds weeks 6 and 7) | Done |
| 6 | ST-GNN architecture | Next |
| 7 | ST-GNN training and tuning (Google Colab) | Next |
| 5 | Backend sync and conflict resolution (FastAPI) | Planned |
| 4 | Mobile app with offline capture (Flutter) | Planned |
| 8 | Risk-aware routing | Planned |
| 9 | Dashboard | Planned |
| 10 to 12 | Integration, validation, report and demo | Planned |

The model comes before the app because routing (week 8) needs the model's output.

## What exists so far

| Script | What it does |
|---|---|
| `week1_graph_and_terrain.py` | Builds the road graph from OpenStreetMap (76 nodes, 151 edges), adds SRTM elevation and slope, saves `nh44_corridor_graph.graphml` and a map |
| `week2a_download_weather.py` | Downloads ERA5-Land weather (2021 to 2025) for the corridor |
| `week2b_process_weather.py` | Converts weather into one table of daily values per road segment, with 3-day and 7-day rainfall |
| `week2c_fill_from_candidates.py` | Looks up coordinates for the sourced disruption events in `data/disruption_candidates.csv` and writes `data/disruption_log.csv` |
| `week2c_disruption_log.py` | Snaps logged events to the nearest NH-44 segment, writes `data/labelled_events.csv` and `data/events_map.png` |
| `week3_offline_schema.sql`, `week3_create_db.py` | Offline SQLite schema (hazard reports, photos, risk cache, sync queue) and a test of it |
| `week4_build_dataset.py` | Builds the model's training tables with a time-based split (train 2021 to 2022, validation 2023, test 2024 to 2025). This is dataset preparation, not the timeline's week 4 (the mobile app) |

## Setup

Python 3.11, on Windows (PowerShell):

```
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
```

### API keys (never commit these)

| Key | Used for | Where it goes |
|---|---|---|
| OpenTopography API key | SRTM elevation (week 1) | `.env` as `OPENTOPO_API_KEY=your_key` |
| Copernicus Climate Data Store token | ERA5-Land weather (week 2) | `C:\Users\<you>\.cdsapirc` |

`.env`, `.cdsapirc`, `venv/`, `cache/` and the large weather files are in `.gitignore`. Check `git status` before every commit.

## Run order

```
python week1_graph_and_terrain.py
python week2a_download_weather.py
python week2b_process_weather.py
python week2c_fill_from_candidates.py
python week2c_disruption_log.py
python week3_create_db.py
python week4_build_dataset.py
```

Before `week2c_fill_from_candidates.py`, fill in `data/place_coordinates.csv` (latitude and longitude of each named place, from Google Maps). Place-name lookup alone puts many events at the town centre.

## Data and sources

- Road network: OpenStreetMap contributors, via OSMnx
- Elevation: SRTM, via OpenTopography
- Weather: ERA5-Land, Copernicus Climate Change Service
- Disruption events: reported incidents from news outlets (Greater Kashmir, The Tribune, Kashmir Life, Deccan Herald, ETV Bharat and others). Every event in `data/disruption_candidates.csv` has a source link. No event is invented or simulated.

## Known limitations

- **Few independent events.** Consecutive-day closures are one disaster logged on several days, so test scores will be rough.
- **Approximate locations.** Event coordinates come from place names, usually village level. Each is marked low or medium confidence.
- **Some dates need checking.** Rows whose notes start with `CHECK DATE` were inferred and should be confirmed from the linked article.
- **Reported events only.** The log leans toward major closures that made the news, so small slides are missing.
- **Sampled negatives.** The training tables keep every real event and sample the other days, so model outputs will be relative risk scores, not true daily probabilities.
- **Coarse weather.** ERA5-Land cells are about 9 km, so neighbouring segments often share the same weather.
- **Coarse terrain.** SRTM is about 30 m resolution, which blurs steep slopes.

## Next steps

1. Confirm the `CHECK DATE` events.
2. Train the ST-GNN in Google Colab and compare it against a rainfall-only baseline.
3. Build the FastAPI backend, then the Flutter app, then routing and the dashboard.