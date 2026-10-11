# RouteWise

Road-disruption risk modelling for a pilot stretch of **NH-44 (Ramban to Banihal, Jammu & Kashmir)**, a landslide-prone highway corridor. The pipeline builds a road graph with terrain, attaches daily weather to each road segment, links reported disruption events to segments, and prepares a dataset for a spatio-temporal graph model (ST-GNN).

> Status: work in progress (Weeks 1 to 4 done). Modelling comes next.

## Pilot corridor

Bounding box: latitude 33.211 to 33.475, longitude 75.161 to 75.262 (about 25 km of NH-44). Graph: 76 nodes, 151 edges.

## Pipeline (run in this order)

| Step | Script | What it does | Main output |
|------|--------|--------------|-------------|
| Week 1 | `week1_graph_and_terrain.py` | Pulls the road network from OpenStreetMap (OSMnx), downloads SRTM elevation from OpenTopography, attaches elevation, slope and road type to every road segment | `nh44_corridor_graph.graphml`, `week1_corridor_map.png` |
| Week 2A | `week2a_download_weather.py` | Downloads ERA5-Land weather data for the corridor | `data/weather/*.nc` (not in Git) |
| Week 2B | `week2b_process_weather.py` | Turns the weather files into daily values per road segment | `data/weather_daily_by_segment.csv` (not in Git) |
| Week 2C | `week2c_fill_from_candidates.py` | Builds `data/disruption_log.csv` from reported events in `data/disruption_candidates.csv`, using hand-checked coordinates from `data/place_coordinates.csv` first, then place-name lookup | `data/disruption_log.csv` |
| Week 2C | `week2c_disruption_log.py` | Snaps each event to the nearest road segment and maps them | `data/disruption_log_snapped.csv`, `data/events_map.png` |
| Week 3 | `week3_create_db.py`, `week3_offline_schema.sql` | Creates the local database from the schema | `data/routewise_local.db` (not in Git) |
| Week 4 | `week4_build_dataset.py` | Builds the modelling dataset | see script *(describe the output here)* |

## Setup

Python 3.11 is recommended.

```
python -m venv venv
venv\Scripts\activate
pip install osmnx rasterio networkx geopandas requests pandas matplotlib
```

Also install the packages that the weather and database scripts import (check the `import` lines at the top of `week2a`, `week2b`, `week3` and `week4`). Once everything runs, save the list with `pip freeze > requirements.txt` and commit it.

### API keys (never commit these)

- **OpenTopography** (elevation): set an environment variable, then open a new terminal.
  ```
  setx OPENTOPO_API_KEY "your-key"
  ```
- **Copernicus Climate Data Store** (ERA5-Land weather): put your key in `~/.cdsapirc`, as described in the CDS API documentation.

`.env`, `.cdsapirc` and `*.key` are listed in `.gitignore`.

## Disruption event data

Events are real, reported incidents (landslides, shooting stones, snow, closures), each with a source link, collected in `data/disruption_candidates.csv`.

To add events:

1. Add a row to `data/disruption_candidates.csv`, with the source URL.
2. If the place isn't found automatically, add a line to `data/place_coordinates.csv` in the form `keyword,lat,lon`. Get the coordinates from Google Maps (right-click the spot on NH-44). The first matching keyword wins, so list specific names above general ones.
3. Run `week2c_fill_from_candidates.py`, then `week2c_disruption_log.py`.

Each event in `disruption_log_snapped.csv` gets an `edge_id` (the road segment), a `snap_dist_m` (distance to that segment in meters) and a `snap_ok` flag (`True` when the event is within 1.5 km of a road).

## Limitations

- **Coordinates are approximate.** Most events come from news reports that name a village or stretch, not an exact location. Rows are marked `location_confidence` of `low` (place-name lookup) or `medium` (hand-checked on Google Maps).
- **Some dates need checking.** Rows whose notes start with `CHECK DATE` were inferred from wording like "Saturday" in the article. Confirm the date at the source link before training on them.
- **Events outside the corridor.** Some reported events (for example around Chanderkote and Dewal) are south of the pilot corridor, so they can't be matched to a road segment. Use `snap_ok` to leave them out of training.
- **Long road segments.** The simplified graph has few nodes, so edges are long and events are concentrated on a few segments. Splitting edges into shorter pieces is planned before modelling.
- **Terrain resolution.** Slope comes from SRTM at 30 m, with elevation sampled at the two ends of each segment, so it understates steepness on winding roads. Edge slope is capped to reduce noise on short edges.

## Repository layout

```
week1_graph_and_terrain.py      road graph + terrain
week2a_download_weather.py      weather download
week2b_process_weather.py       weather per segment
week2c_fill_from_candidates.py  event log builder
week2c_disruption_log.py        event snapping + map
week3_create_db.py              local database
week3_offline_schema.sql        database schema
week4_build_dataset.py          dataset builder
data/                           event files, snapped events, map
```

Generated or large files (weather `.nc` files, DEM `.tif`, the weather CSV and the local database) are not tracked in Git. Re-create them with the scripts above.

## Data sources

- Road network: OpenStreetMap contributors (via OSMnx)
- Elevation: SRTM, via the OpenTopography API
- Weather: ERA5-Land, Copernicus Climate Change Service
- Disruption events: news reports, each listed with its source link in the CSV
