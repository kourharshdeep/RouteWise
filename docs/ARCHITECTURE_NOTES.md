# RouteWise System Architecture & Reconnaissance Notes

**Date:** 2026-11-11
**Branch:** `feature/realtime-intelligence`
**Corridor:** NH-44 Ramban–Banihal section (151 segments, ~36 km)

---

## 1. Repository Layout & Frameworks
- **Backend:** FastAPI (Python 3.11), Uvicorn ASGI server, Pydantic v2 schemas, SQLite (`data/routewise_local.db` for protected historical data; `data/runtime/routewise_live.db` for runtime operations).
  - *Bootstrap command:* `python -m app.bootstrap_db` (idempotent DDL + loads 274k segment_weather rows)
  - *Run command:* `python -m uvicorn src.api.app:app --host 127.0.0.1 --port 8000 --reload`
  - *Test command:* `python -m pytest` (206 passing unit & integration tests across all modes: `off`, `replay`, `live`, plus 34 incident deduplication tests in `tests/test_incident_deduplication.py` and 6 historical golden tests in `tests/test_journey_golden.py`)
  - *Dependencies:* `requirements.txt` (FastAPI, PyTorch, scikit-learn, networkx, pytest, Pillow) and `requirements-pipeline.txt` (offline GIS & atmospheric ingestion: osmnx, rasterio, cdsapi, netCDF4, geopandas).
- **Frontend:** React 18, Vite, React Router DOM v6, React-Leaflet v4, Lucide React icons, Vanilla CSS design tokens.
  - *Run command:* `cd frontend && npm run dev`
  - *Test command:* `npm --prefix frontend test` (49 passing unit tests across 14 test suites via `node --test test/unit.test.js`)
  - *Build command:* `npm --prefix frontend run build` (Vite v6.4.4 production bundle)
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
- **Protected Historical Database:** SQLite at `data/routewise_local.db` (SHA-256: `917A1C475E2FF2D8D9E877F9321BEDF1D99F1877D446EE4667D86FA3E3D96BC6`). Protected by fail-closed guard `_is_protected_db()`; runtime operations and test runs are forbidden from modifying it.
- **Runtime Operational Database:** SQLite at `data/runtime/routewise_live.db` (git-ignored). Houses all live observations, hazard events, live risk scores, and alerts.
- **Initialization:** `python -m app.bootstrap_db` idempotently runs schema DDL, creates performance indexes, and populates `segment_weather` from `data/weather_daily_by_segment.csv`.
- **Core Tables:**
  - `users`: `id`, `email`, `name`, `password_hash`, `salt`, `role`, `preferred_vehicle`, `created_at`, `is_simulated`.
  - `reports`: UUID primary key, `client_uuid` idempotency key, `reporter_id`, `category`, `description`, `latitude`, `longitude`, `nearest_segment_id`, `nearest_segment_distance_m`, `photo_path`, `status`, `assigned_to`, `client_created_at`, `created_at`, `updated_at`, `is_simulated`, `duplicate_of` (references primary report UUID for duplicates), `hazard_event_id` (references linked active hazard event).
  - `report_status_history`: append-only audit trail (`id`, `report_id`, `from_status`, `to_status`, `actor_id`, `actor_role`, `note`, `timestamp`).
  - `segment_weather`: pre-populated daily ERA5-Land reanalysis per segment (274,971 records).

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
  - `POST /api/v1/journey/plan` (chainage-ordered routing with multi-factor risk scoring, hold advisories, and live date substitution metadata)
- **Live Intelligence & Telemetry:**
  - `GET /api/v1/live/status` (telemetry age, provider, current mode, weather window)
  - `GET /api/v1/live/risk` (current live segment risk & operational status)
  - `GET /api/v1/live/changes` (incremental risk changes since timestamp)
  - `GET /api/v1/live/stream` (real-time Server-Sent Events stream with 20s heartbeats)
- **Hazard Events & Overlays:**
  - `GET /api/v1/events/active` (public active hazard events)
  - `POST /api/v1/events/simulate` (admin only; simulates hazard presets on segments)
  - `POST /api/v1/events/simulate/clear` (admin only; purges simulated hazard events)
- **Alerts & Scenario Player:**
  - `GET /api/v1/alerts/active`, `GET /api/v1/alerts/history` (active & historical corridor alerts)
  - `POST /api/v1/alerts/{id}/acknowledge`, `POST /api/v1/alerts/{id}/clear` (patrol/admin only)
  - `POST /api/v1/alerts/scenario/step` (admin only; advances monsoon storm scenario)
- **Field Reports & Patrol:**
  - `POST /api/v1/reports` (submit report; authenticated user/patrol, client-UUID idempotent, deduplication linking)
  - `GET /api/v1/reports` (list all reports; patrol/admin only)
  - `GET /api/v1/reports/mine` (list own submitted reports; user/patrol)
  - `GET /api/v1/reports/public` (verified hazards visible publicly)
  - `GET /api/v1/reports/summary` (dispatch overview status counts; patrol/admin)
  - `GET /api/v1/reports/{report_id}` (detailed report view)
  - `GET /api/v1/reports/{report_id}/photo` (authenticated photo evidence retrieval)
  - `PATCH /api/v1/reports/{report_id}/status` (state machine transition: submitted -> verified -> assigned -> resolved, or rejected)
  - `PATCH /api/v1/reports/{report_id}/assign` (assign unit)
- **Disruptions & Assistant:**
  - `GET /api/v1/disruptions`, `GET /api/v1/disruptions/stats` (99 historical snapped events)
  - `POST /api/v1/chat/query` (natural language corridor assistant)

---

## 5. Pipeline Data & Environmental Exposure
- **Exposed Risk Output:** `segment_id`, `risk_score` (0.0 to 1.0), `risk_tier` (`Low`, `Medium`, `High`), `status`.
- **Static Terrain Data:** `data/segment_static.csv` exposes `slope_mean_deg` / `slope`, `elevation_mean_m` / `elevation_m`, `length_m`.
- **Weather Data:** `data/weather_daily_by_segment.csv` holds daily ERA5-Land reanalysis for 2021–2025 (`precip_mm`, `snowfall_mm_we`, `temp_mean_c`, `temp_min_c`, `snow_depth_m`, `precip_3d_mm`, `precip_7d_mm`).
- **Nature of Predictions:** Strictly retrospective historical backtest over historical dates (2021-01-06 to 2025-12-31). When live mode is active, live weather from Open-Meteo is evaluated by ST-GNN under explicit **"Experimental - not validated"** disclaimers.

---

## 6. Road Graph & Routing Topology
- **Topology:** The NH-44 Ramban–Banihal graph is a single continuous linear corridor. No parallel highway alternatives exist within the corridor graph model.
- **Routing Reality:** Array slicing represents the physical path along the highway. True multi-path alternatives (such as Mughal Road) do not have road network graph data in this repository and must not be fabricated. The router strictly enforces `has_alternative=False` and provides honest operational recommendations (`HOLD`, `DELAY`, `PROCEED_WITH_CAUTION`, `PROCEED`, `NO_DATA`) without citing zero counts as causes.

---

## 7. Theming & Hardcoded Colors
- **Design System:** Centralized CSS custom properties in `frontend/src/theme.css` and `frontend/src/App.css` reacting to `data-theme="dark"` and `data-theme="light"`.
- **Accessibility:** All accent and status combinations are verified for WCAG AA compliance (minimum 4.5:1 for normal text, 3.0:1 for large UI components). Non-color symbols (`●`, `■`, `▲`, `?`, `~`) accompany all tier cues for color-blind accessibility.

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
- **Single Corridor Reality:** The NH-44 Ramban–Banihal section is essentially a single-corridor mountain highway without alternate bypasses. If a segment is blocked, routing outputs strictly advise "HOLD" or "DELAY" rather than fabricating non-existent detours.

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

---

## 10. Real-Time Data Pipeline & Streaming Architecture (Steps 1–7)

### End-to-End Data Flow

```text
[Weather Source]
  ├── ReplayProvider (data/weather_daily_by_segment.csv)
  └── OpenMeteoProvider (Open-Meteo REST API, 22 clusters)
        │
        ▼
[Runtime Storage: data/runtime/routewise_live.db]
  └── weather_observation (7 dynamic features, quality flags, idempotent upsert)
        │
        ▼
[LiveRiskService]
  ├── 7-day rolling feature window construction (weather_window_end = yesterday_utc)
  ├── ST-GNN wrapping (stgnn_best.pt, SHA-256 verified)
  ├── Fail-safe evaluation (<7d -> UNKNOWN, >24h -> STALE_DATA)
  └── live_risk table (score, tier, model_version, computed_at)
        │
        ▼
[Operational Synthesis & Monitoring]
  ├── HazardEventService: hazard_event table (field reports, simulated, TCU)
  │     └── derived operational_status (CLOSED, RESTRICTED, UNKNOWN, CAUTION, OPEN)
  ├── AlertService: alert table (de-duplication, 1-hr cooldown, auto-clearance)
  └── JourneyService: MultiObjectiveRouter (baseline vs risk-aware, HOLD/DELAY)
        │
        ▼
[Real-Time Dispatch: LiveBroadcaster]
  └── SSE Endpoint: GET /api/v1/live/stream
        ├── Heartbeat (every 20s)
        ├── risk_update
        ├── event_update
        ├── alert
        ├── route_update
        └── status
              │
              ▼
[Frontend: React 18 Dashboard]
  ├── Live Connection Resilience (SSE reconnect with full jitter, capping at 30s)
  ├── Polling Fallback (REST polling every 10s-30s when stream interrupted)
  ├── LiveBanner ("Experimental - not validated", telemetry age, amber stale)
  ├── CorridorStrip & CorridorMap (in-place animated updates, non-color cues)
  ├── JourneyPlanner (mode-aware planning, live date substitution notice, HOLD)
  └── AlertDrawer & ScenarioPlayer (bilingual alerts, patrol ack/clear)
```

### Runtime Database Schemas (`data/runtime/routewise_live.db`)

1. **`weather_observation`**:
   - `segment_id TEXT`, `obs_date TEXT`, `precip_mm REAL`, `snowfall_mm_we REAL`, `temp_mean_c REAL`, `temp_min_c REAL`, `snow_depth_m REAL`, `precip_3d_mm REAL`, `precip_7d_mm REAL`, `source TEXT`, `fetched_at TEXT`, `quality_flag TEXT`
   - Primary Key: `(segment_id, obs_date, source)`
   - Indexes: `idx_weather_obs_date (obs_date)`, `idx_weather_segment (segment_id)`

2. **`live_risk`**:
   - `id INTEGER PRIMARY KEY AUTOINCREMENT`, `segment_id TEXT`, `as_of TEXT`, `score REAL`, `tier TEXT`, `status TEXT`, `model_version TEXT`, `checkpoint_sha256 TEXT`, `weather_window_end TEXT`, `computed_at TEXT`
   - Primary Key: `(segment_id, as_of)`
   - Indexes: `idx_live_risk_segment_asof (segment_id, as_of)`

3. **`hazard_event`**:
   - `id TEXT PRIMARY KEY`, `segment_id TEXT`, `hazard_type TEXT`, `severity TEXT`, `status TEXT`, `origin TEXT`, `is_simulated INTEGER`, `source_report_id TEXT`, `starts_at TEXT`, `expires_at TEXT`, `created_by TEXT`, `created_at TEXT`, `closed_at TEXT`, `report_count INTEGER DEFAULT 1`, `last_reported_at TEXT`
   - Indexes: `idx_hazard_active (status, segment_id)`

4. **`hazard_event_history`**:
   - `id INTEGER PRIMARY KEY AUTOINCREMENT`, `event_id TEXT`, `action TEXT`, `actor_id TEXT`, `actor_role TEXT`, `note TEXT`, `timestamp TEXT`

5. **`alert`**:
   - `id TEXT PRIMARY KEY`, `segment_id TEXT`, `alert_type TEXT`, `severity TEXT`, `title_en TEXT`, `title_hi TEXT`, `message_en TEXT`, `message_hi TEXT`, `status TEXT`, `created_at TEXT`, `acknowledged_at TEXT`, `acknowledged_by TEXT`, `cleared_at TEXT`, `cleared_by TEXT`, `cooldown_until TEXT`
   - Indexes: `idx_alert_active (status, segment_id, alert_type)`

---

## 11. Incident Intelligence, Deduplication & Linking Architecture (Task 4)

### 11.1 Additive Schema Migration
To maintain backward compatibility with existing tests and datasets:
- Columns added to `reports`:
  - `duplicate_of TEXT REFERENCES reports(id)`: Points strictly to the primary report's UUID if this submission is a corroborating duplicate.
  - `hazard_event_id TEXT REFERENCES hazard_event(id)`: Points to the active hazard event generated or linked.
- Columns added to `hazard_event`:
  - `report_count INTEGER DEFAULT 1`: Total number of corroborating reports linked to the active event.
  - `last_reported_at TEXT`: UTC ISO timestamp of the most recent verified corroborating report.

### 11.2 Protected Database Safety Guard
`_is_protected_db(path)` in `src/services/report_service.py` prevents tests or app execution from mutating historical assets:
```python
def _is_protected_db(path: Optional[Path]) -> bool:
    if path is None:
        return False
    try:
        resolved = Path(path).resolve()
        protected = Path("data/routewise_local.db").resolve()
        return resolved == protected
    except Exception:
        return True  # Fail closed: treat unresolvable paths as protected
```

### 11.3 Category Normalization & Presets Fallback
The public API accepts 7 `ReportCategory` values: `landslide`, `shooting_stones`, `flooding`, `road_damage`, `snow_or_ice`, `single_lane_or_obstruction`, `other`.
- **Presets (`VALID_PRESETS`):** `landslide`, `shooting_stones`, `flooding`, `road_damage`. Submissions with these categories retain their type and create independent hazard events.
- **Fallback Normalization:** `other`, `snow_or_ice`, and `single_lane_or_obstruction` fall back to `road_damage`. When submitted on a segment with an active `road_damage` event, they merge into it as duplicates.

### 11.4 Dual Timestamp Window & Verified Extension
Deduplication candidate evaluation checks:
```sql
WHERE segment_id = :segment_id
  AND hazard_type = :hazard_type
  AND COALESCE(is_simulated, 0) = :is_simulated
  AND status = 'active'
  AND expires_at > :now
  AND (created_at >= :dedup_limit OR (last_reported_at IS NOT NULL AND last_reported_at >= :dedup_limit))
ORDER BY created_at ASC
LIMIT 1
```
- **Verified-Only Extension:** `last_reported_at` updates and extends the deduplication window only when a patrol officer or administrator marks a report as `verified`. Unverified or guest submissions cannot extend event lifecycles.

### 11.5 Primary vs. Duplicate Rejection Policies
- **Rejecting the Primary Report:** Transitions the active hazard event to `closed`. If other reports were linked, their underlying records remain independently preserved in `reports`.
- **Rejecting a Duplicate Report:** Sets `duplicate_of = NULL` on that report, leaving the active hazard event open.

### 11.6 Accurate Route Explanation Formatting
Routing explanations dynamically distinguish:
1. `HOLD`: Corridor blocked by $N$ closed segment(s) (names listed; never citing 0).
2. `NO_DATA`: Route includes $N$ unmonitored segment(s) or live telemetry is stale (>24h).
3. `DELAY`: High disruption tier ($\ge 0.35$) on $N$ segment(s) or peak score reaches threshold.
4. `PROCEED_WITH_CAUTION`: Elevated tier ($0.10 - 0.35$) on $N$ segment(s).
5. `PROCEED`: Baseline clear ($< 0.10$).

---

## 12. Frontend Connection Resilience & Error Boundary (Tasks 3b–3c)

### 12.1 Connection Lifecycle
`connectionResilience.js` manages frontend SSE lifecycle transitions:
- `connected`: Active SSE stream receiving heartbeats.
- `reconnecting`: Exponential backoff with full jitter, capping at 30s.
- `polling`: REST polling fallback (10s–30s interval) when SSE stream drops.
- `offline`: Browser network offline.

### 12.2 React Error Boundary
`ErrorBoundary.jsx` wraps the application tree, capturing render failures, logging component stacks, and rendering translated localized fallbacks (`error_boundary.title`, `error_boundary.message`, `error_boundary.reload`).
