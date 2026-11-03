# RouteWise System Architecture & Reconnaissance Notes

**Date:** 2026-10-14  
**Branch:** `feature/patrol-ops-and-demo`  
**Corridor:** NH-44 Ramban–Banihal section (151 segments, ~36 km)

---

## 1. Repository Layout & Frameworks
- **Backend:** FastAPI (Python 3.11), Uvicorn server, Pydantic v2 schemas, SQLite (`data/routewise_local.db`).
  - *Bootstrap command:* `python -m app.bootstrap_db` (idempotent DDL + loads 274k segment_weather rows)
  - *Run command:* `python -m uvicorn src.api.app:app --host 127.0.0.1 --port 8000 --reload`
  - *Test command:* `python -m pytest` (61 passing unit & integration tests across 12 modules)
  - *Dependencies:* `requirements.txt` (FastAPI, PyTorch, scikit-learn, networkx, pytest) and `requirements-pipeline.txt` (offline GIS & atmospheric ingestion: osmnx, rasterio, cdsapi, netCDF4, geopandas).
- **Frontend:** React 18, Vite, React Router DOM v6, React-Leaflet v4, Lucide React icons, Vanilla CSS design tokens.
  - *Run command:* `cd frontend && npm run dev`
  - *Test command:* `npm --prefix frontend test` (13 passing unit tests via `node --test`)
- **Machine Learning Core:** PyTorch ST-GNN (2-layer GCNConv + GRU recurrent cell + linear projection), model weights in `stgnn_best.pt` (SHA-256: `68B04504EAE6062C84927917C05168C34FD17823BA5EF5C13F963D335054006E`).

---

## 2. Authentication & Authorization State
- **Password Hashing:** PBKDF2-HMAC-SHA256 with 100,000 iterations and per-user 16-byte random salt.
- **Tokens:** Custom HS256-signed JWTs with 72-hour default expiration (12 hours for guest).
- **Roles in Database:** `role` column in `users` table (`guest`, `user`, `patrol`, `admin`).
- **Access Enforcement:** Strict role normalization enforced in FastAPI backend dependencies (`src/api/dependencies.py`). Public registration is strictly forced to role `user`.
- **Patrol Provisioning:** CLI utility `python -m app.create_patrol` (prompts via `getpass.getpass`, passwords never printed) or admin role promotion endpoint.
- **Guest Access:** `POST /api/v1/auth/guest` issues signed token with `sub="0"` and `role="guest"`. Strictly read-only on all backend write endpoints.

---

## 3. Data Storage & Schema Evolution
- **Database:** SQLite at `data/routewise_local.db`.
- **Initialization:** `python -m app.bootstrap_db` idempotently runs schema DDL, creates performance indexes, and populates `segment_weather` from `data/weather_daily_by_segment.csv`.
- **Core Tables:**
  - `users`: `id`, `email`, `name`, `password_hash`, `salt`, `role`, `preferred_vehicle`, `created_at`, `is_simulated`.
  - `reports`: UUID primary key, `client_uuid` idempotency key, `reporter_id`, `category`, `description`, `latitude`, `longitude`, `nearest_segment_id`, `nearest_segment_distance_m`, `photo_path`, `status`, `assigned_to`, `client_created_at`, `created_at`, `updated_at`, `is_simulated`.
  - `report_status_history`: append-only audit trail (`id`, `report_id`, `from_status`, `to_status`, `actor_id`, `actor_role`, `note`, `timestamp`).
  - `segment_weather`: pre-populated daily ERA5-Land reanalysis per segment (274k records).

---

## 4. API Endpoints & Consumption (Verified against /docs)
- **Root & Health:** `GET /`, `GET /api/health`
- **Auth:**
  - `POST /api/v1/auth/register` (strictly forces `user` role)
  - `POST /api/v1/auth/login`
  - `POST /api/v1/auth/guest`
  - `GET /api/v1/auth/me`
  - `PUT /api/v1/auth/profile`
  - `GET /api/v1/auth/demo-accounts` (only active when `ROUTEWISE_DEMO_MODE=true`; never returns passwords)
  - `PATCH /api/v1/auth/users/{user_id}/role` (admin only)
- **Corridor & Features:**
  - `GET /api/v1/corridor/segments` (151 NH-44 segment geometries & metadata)
  - `GET /api/v1/corridor/segments/{segment_id}/features` (elevation, slope, precipitation)
  - `GET /api/v1/corridor/advisories` (official police & TCU alerts)
  - `GET /api/v1/corridor/services` (emergency, hospital, recovery facilities)
  - `GET /api/v1/corridor/weather` (corridor-wide weather summaries)
- **Risk Evaluation:**
  - `GET /api/v1/risk` (retrospective disruption risk scores for observation dates)
  - `GET /api/v1/risk/dates` (catalog of 1,821 historical observation dates)
- **Journey Planner:**
  - `GET /api/v1/journey/places` (landmarks along NH-44)
  - `POST /api/v1/journey/plan` (chainage-ordered routing with multi-factor risk scoring and hold advisories)
- **Disruptions:**
  - `GET /api/v1/disruptions`, `GET /api/v1/disruptions/stats` (99 historical snapped events)
- **Field Reports & Patrol:**
  - `POST /api/v1/reports` (submit report; authenticated user/patrol, client-UUID idempotent)
  - `GET /api/v1/reports` (list all reports; patrol/admin only)
  - `GET /api/v1/reports/mine` (list own submitted reports; user/patrol)
  - `GET /api/v1/reports/public` (verified hazards visible publicly)
  - `GET /api/v1/reports/summary` (dispatch overview status counts; patrol/admin)
  - `GET /api/v1/reports/{report_id}` (detailed report view)
  - `GET /api/v1/reports/{report_id}/photo` (authenticated photo evidence retrieval)
  - `PATCH /api/v1/reports/{report_id}/status` (state machine transition: submitted -> verified -> assigned -> resolved, or rejected)
  - `PATCH /api/v1/reports/{report_id}/assign` (assign unit)
- **Assistant:**
  - `POST /api/v1/chat/query` (natural language corridor assistant)

---

## 5. Pipeline Data & Environmental Exposure
- **Exposed Risk Output:** `segment_id`, `risk_score` (0.0 to 1.0), `risk_tier` (`Low`, `Medium`, `High`), `status`.
- **Static Terrain Data:** `data/segment_static.csv` exposes `slope_mean_deg` / `slope`, `elevation_mean_m` / `elevation_m`, `length_m`.
- **Weather Data:** `data/weather_daily_by_segment.csv` holds daily ERA5-Land reanalysis for 2021–2025 (`precip_mm`, `snowfall_mm_we`, `temp_mean_c`, `temp_min_c`, `snow_depth_m`, `precip_3d_mm`, `precip_7d_mm`).
- **Nature of Predictions:** Strictly retrospective historical backtest over historical dates (2021-01-06 to 2025-12-31). The pipeline is not connected to a live operational numerical forecast service for future dates.

---

## 6. Road Graph & Routing Topology
- **Topology:** The NH-44 Ramban–Banihal graph is a single continuous linear corridor. No parallel highway alternatives exist within the corridor graph model.
- **Routing Reality:** Array slicing represents the physical path along the highway. True multi-path alternatives (such as Mughal Road) do not have road network graph data in this repository and must not be fabricated. Safest-vs-fastest comparison will be implemented with genuine single-corridor trade-off metrics, date/time sensitivity, and verified synthetic graph unit tests for multi-objective Dijkstra.

---

## 7. Theming & Hardcoded Colors
- **Design System:** Centralized CSS custom properties in `frontend/src/theme.css` and `frontend/src/App.css` reacting to `data-theme="dark"` and `data-theme="light"`.
- **Hardcoded Colors:** 11 hardcoded hex color values identified in `frontend/src/components/CorridorMap.jsx` (0 in other components). These will be refactored into semantic tokens during Phase 7.

---

## 8. Real-Time Intelligence Architecture (Live & Replay Modes)

### Mode Configuration (`ROUTEWISE_LIVE_MODE`)
- `off` (Default): All real-time background fetchers and live schedulers remain inactive. The application operates strictly in historical mode with 100% existing API parity.
- `replay`: Weather observations are replayed from historical ERA5-Land reanalysis (`data/weather_daily_by_segment.csv`) as if live, isolated into the runtime database `data/runtime/routewise_live.db`.
- `live`: Live weather observations are fetched from the external provider (Open-Meteo), converted to ERA5-Land units, rolled into 7-day feature windows, and passed to the existing ST-GNN inference engine.

### Runtime Isolation
- All live observations, hazard events, live risk scores, and alerts are stored in `data/runtime/routewise_live.db` (git-ignored).
- Historical assets (`data/routewise_local.db`, `data/*.csv`, `cache/`) are strictly read-only protected assets and never modified by live operations.

### Honest Framing & Distribution Shift Guarantees
- **Distribution Shift:** The PyTorch ST-GNN model was trained on ERA5-Land atmospheric reanalysis. Live numerical weather forecasts/observations represent a distribution shift. All live predictions are explicitly badged **"Experimental - not validated"** across API payloads and user interfaces.
- **Relative Risk Index:** Prediction scores represent an advisory relative-risk index (0.0 to 1.0) and must never be presented as physical failure probabilities.
- **Fail-Safe Integrity:** Missing or stale data (< 7 days of weather, or observation older than 24 hours) is evaluated as `UNKNOWN` or `STALE_DATA`, never as `Low` risk.
- **Simulated Hazards:** Any operator-simulated incident is explicitly badged `is_simulated=true` / `SIMULATED` and will never enter historical training datasets.
- **Single Corridor Reality:** The NH-44 Ramban–Banihal section is essentially a single-corridor mountain highway without alternate bypasses. If a segment is blocked, routing outputs must advise "HOLD" or "DELAY" rather than fabricating non-existent detours.

---

## 9. Operational Status Rule Table & Hazard Event Overlay (Task 2 / Step 4)

### Architectural Principle: Overlay Separation
Hazard events (field reports, operator simulations, official TCU advisories) act as an **operational overlay**. They **never modify model weights, model input tensors, or calculated ST-GNN risk scores**. The API returns both `model_risk` and `active_events[]`, synthesizing them into a derived `operational_status`.

### Deterministic Operational Status Rule Table

| Priority | Evaluated Condition | Resulting `operational_status` | Operational Meaning |
|:---:|---|:---:|---|
| **1** | Any active event with `severity == 'critical'` OR `hazard_type in ('landslide', 'flooding')` | **`CLOSED`** | Road physically blocked or impassable. Traffic must hold. |
| **2** | Any active event with `hazard_type in ('single_lane', 'single-lane')` OR `severity == 'high'` OR (`hazard_type in ('shooting_stones', 'snow_ice', 'road_damage')` AND `severity == 'medium'`) | **`RESTRICTED`** | Reduced capacity, convoys, or severe slowdown. Proceed with caution. |
| **3** | Model input is missing (< 7 days) or stale (> 24h) AND no critical/blocking physical event | **`UNKNOWN`** | Telemetry deficit: advisory status cannot be safely determined. Never defaults to Low/Open. |
| **4** | Active event with `severity in ('low', 'medium')` OR `model_risk.risk_tier in ('Medium', 'High')` | **`CAUTION`** | Elevated hazard potential or minor localized disturbance. |
| **5** | `model_risk.risk_tier == 'Low'` AND zero active events on the segment | **`OPEN`** | Normal operational flow under standard advisory guidelines. |

### Event Lifecycle & Governance Rules
1. **Unverified Field Reports:** Public reports in status `submitted` **NEVER** generate public hazard events or alter operational status.
2. **Verification Promotion:** When a patrol officer or administrator marks a report as `verified` or `assigned`, an active event is created or refreshed with a 24-hour default expiration.
3. **Closure & Rejection:** Marking a report as `resolved` or `rejected` immediately transitions associated events to status `closed`.
4. **Auto-Expiry Audit Trail:** Active events exceeding `expires_at` are transitioned to `expired` by background workers, appending an immutable record to `hazard_event_history`.
5. **Simulated Hazards Containment:** Operator simulations (`POST /api/v1/events/simulate`) are restricted exclusively to administrators (HTTP 403 otherwise). Simulated records have `is_simulated=1`, badge `SIMULATED`, reside solely in `data/runtime/routewise_live.db`, and are purged with `POST /api/v1/events/simulate/clear`.


