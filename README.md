# RouteWise

Predictive, offline-first route safety for **NH-44 in Jammu & Kashmir**.
RouteWise models landslide, snow and shooting-stone disruption risk for each road segment of the highway, so that routes can later be chosen on predicted safety and not just distance. It is a minor project (Group 21, MIET Jalandhar).

**Pilot corridor:** Ramban to Banihal (latitude 33.211 to 33.475, longitude 75.161 to 75.262), a landslide-prone stretch of the Jammu-Srinagar highway.

**Status:** work in progress. Weeks 1 to 3 of the project timeline are done, plus the dataset preparation and the ST-GNN model (weeks 6 and 7). The FastAPI backend (week 5) is next.

## Project plan and progress

| Timeline week | Topic                                          | Status  |
| ------------- | ---------------------------------------------- | ------- |
| 1             | GIS data and NH-44 graph                       | Done    |
| 2             | Weather and historical disruption data         | Done    |
| 3             | Offline-first SQLite schema                    | Done    |
| Prep          | Dataset for the model (feeds weeks 6 and 7)    | Done    |
| 6             | ST-GNN architecture and baselines              | Done    |
| 7             | ST-GNN training and tuning (Google Colab)      | Done    |
| 5             | Backend sync and conflict resolution (FastAPI) | Next    |
| 4             | Mobile app with offline capture (Flutter)      | Planned |
| 8             | Risk-aware routing                             | Planned |
| 9             | Dashboard                                      | Planned |
| 10 to 12      | Integration, validation, report and demo       | Planned |

The model comes before the app because routing (week 8) needs the model's output.

## What exists so far

| Script                                           | What it does                                                                                                                                                                                 |
| ------------------------------------------------ | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `week1_graph_and_terrain.py`                     | Builds the road graph from OpenStreetMap (76 nodes, 151 edges), adds SRTM elevation and slope, saves `nh44_corridor_graph.graphml` and a map                                                 |
| `week2a_download_weather.py`                     | Downloads ERA5-Land weather (2021 to 2025) for the corridor                                                                                                                                  |
| `week2b_process_weather.py`                      | Converts weather into one table of daily values per road segment, with 3-day and 7-day rainfall                                                                                              |
| `week2c_fill_from_candidates.py`                 | Looks up coordinates for the sourced disruption events in `data/disruption_candidates.csv` and writes `data/disruption_log.csv`                                                              |
| `week2c_disruption_log.py`                       | Snaps logged events to the nearest NH-44 segment, writes `data/labelled_events.csv` and `data/events_map.png`                                                                                |
| `week3_offline_schema.sql`, `week3_create_db.py` | Offline SQLite schema (hazard reports, photos, risk cache, sync queue) and a test of it                                                                                                      |
| `week4_build_dataset.py`                         | Builds the model's training tables with a time-based split (train 2021 to 2022, validation 2023, test 2024 to 2025). This is dataset preparation, not the timeline's week 4 (the mobile app) |
| `week6_stgnn.py`                                 | Builds 7-day weather windows per segment, defines the ST-GNN, and fits two logistic-regression baselines. Writes `week6_baseline_metrics.json`                                               |
| `week7_train.py`                                 | Trains the ST-GNN over 5 random seeds with early stopping, scores it on the held-out years, and saves `stgnn_best.pt` and `stgnn_metrics.json`                                               |

## Setup

Python 3.11, on Windows (PowerShell):

```
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
```

The model scripts (weeks 6 and 7) are run in Google Colab, where PyTorch is already installed, so PyTorch is not needed for the earlier steps.

### API keys (never commit these)

| Key                                 | Used for                   | Where it goes                         |
| ----------------------------------- | -------------------------- | ------------------------------------- |
| OpenTopography API key              | SRTM elevation (week 1)    | `.env` as `OPENTOPO_API_KEY=your_key` |
| Copernicus Climate Data Store token | ERA5-Land weather (week 2) | `C:\Users\<you>\.cdsapirc`            |

`.env`, `.cdsapirc`, `venv/`, `cache/` and the large weather files are in `.gitignore`. Check `git status` before every commit.

## Run order

On your computer:

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

In Google Colab (weeks 6 and 7):

1. Upload `training_samples.csv`, `segment_static.csv`, `segment_adjacency.csv`, `weather_daily_by_segment.csv`, `week6_stgnn.py` and `week7_train.py` to one Drive folder.
2. Open a notebook, mount Drive and go to that folder:

```
from google.colab import drive
drive.mount('/content/drive')
%cd /content/drive/MyDrive/RouteWise/model
```

3. Run the checks, baselines and training:

```
!python week6_stgnn.py --check
!python week6_stgnn.py
!python week7_train.py --data-dir . --out-dir .
```

4. Download `stgnn_best.pt`, `stgnn_metrics.json` and `week6_baseline_metrics.json` back into the project folder.

## Model (weeks 6 and 7)

**Architecture.** For each of the 151 road segments the model reads the previous 7 days of weather (rainfall log-scaled, all features standardised using pre-2023 statistics only). A graph convolution mixes each segment's features with its neighbours' (from `segment_adjacency.csv`), a GRU reads the 7 days in order, and a small head combines the result with the static segment features (length, slope, elevation, primary-road flag) to output a risk score.

**Training.** Weighted binary cross-entropy, because disruptions are rare. Early stopping on the 2023 validation year (average precision). The run is repeated over 5 random seeds and the mean and spread are reported.

**Data split** (samples and real events in each):

| Split      | Years        | Samples | Events |
| ---------- | ------------ | ------- | ------ |
| Train      | up to 2022   | 855     | 28     |
| Validation | 2023         | 434     | 14     |
| Test       | 2024 to 2025 | 680     | 22     |

**Tuning.** A small search over hidden size (16, 32, 64) and learning rate (1e-3, 3e-3). The final setting is hidden size 32, dropout 0.2 and learning rate 3e-3, chosen by mean validation average precision, not by test score.

**Results** (test years 2024 to 2025, average precision, higher is better):

| Model                             | Test AP         |
| --------------------------------- | --------------- |
| Random guessing (base rate)       | 0.032           |
| Rainfall-only logistic regression | 0.105           |
| All-features logistic regression  | 0.174           |
| ST-GNN (mean of 5 seeds)          | 0.215 +/- 0.041 |

The ST-GNN is about 7 times better than random guessing and about 2 times better than the rainfall-only baseline. Its edge over the all-features logistic regression is small compared with the spread between seeds, and the test set has only 22 events, so these scores are rough.

**Outputs.**

| File                          | What it holds                                                                           |
| ----------------------------- | --------------------------------------------------------------------------------------- |
| `stgnn_best.pt`               | Model weights, normalisation statistics, segment order and column names, saved together |
| `stgnn_metrics.json`          | Per-seed and mean scores of the final model, plus the baselines                         |
| `stgnn_metrics_default.json`  | Scores of the earlier run with default settings (learning rate 1e-3)                    |
| `week6_baseline_metrics.json` | Scores of the two logistic-regression baselines                                         |

## Data and sources

- Road network: OpenStreetMap contributors, via OSMnx
- Elevation: SRTM, via OpenTopography
- Weather: ERA5-Land, Copernicus Climate Change Service
- Disruption events: reported incidents from news outlets (Greater Kashmir, The Tribune, Kashmir Life, Deccan Herald, ETV Bharat and others). Every event in `data/disruption_candidates.csv` has a source link. No event is invented or simulated.

## Known limitations

- **Few independent events.** Consecutive-day closures are one disaster logged on several days. There are only 22 events in the test years, so test scores are rough and differences between models are often within the noise.
- **Approximate locations.** Event coordinates come from place names, usually village level. Each is marked low or medium confidence.
- **Some dates need checking.** Rows whose notes start with `CHECK DATE` were inferred and should be confirmed from the linked article.
- **Reported events only.** The log leans toward major closures that made the news, so small slides are missing.
- **Sampled negatives.** The training tables keep every real event and sample the other days, so model outputs are relative risk scores, not true daily probabilities.
- **Coarse weather.** ERA5-Land cells are about 9 km, so neighbouring segments often share the same weather.
- **Coarse terrain.** SRTM is about 30 m resolution, which blurs steep slopes.

## Next steps

1. Build the FastAPI backend (week 5): `/risk` serving the model's scores, `/reports` accepting field reports, duplicate prevention and last-write-wins sync.
2. Build the Flutter app with offline capture (week 4).
3. Add risk-aware routing (week 8) and the dashboard (week 9).
4. Confirm the `CHECK DATE` events and rerun the dataset and model if any date changes.
5. Integration test, validation, final report and demo (weeks 10 to 12).
