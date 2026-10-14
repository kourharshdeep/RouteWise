# RouteWise System Architecture & Reconnaissance Notes

**Date:** 2026-10-14  
**Branch:** `feature/patrol-ops-and-demo`  
**Corridor:** NH-44 Ramban–Banihal section (151 segments, ~36 km)

---

## 1. Repository Layout & Frameworks
- **Backend:** FastAPI (Python 3.11), Uvicorn server, Pydantic v2 schemas, SQLite (`data/routewise_local.db`).
  - *Run command:* `.\venv\Scripts\uvicorn src.api.app:app --host 127.0.0.1 --port 8000 --reload`
  - *Test command:* `.\venv\Scripts\python.exe -m pytest -p no:cacheprovider`
- **Frontend:** React 18, Vite, React Router DOM v6, React-Leaflet v4, Lucide React icons, Vanilla CSS design tokens.
  - *Run command:* `cd frontend && npm run dev`
- **Machine Learning Core:** PyTorch ST-GNN (2-layer GCNConv + GRU recurrent cell + linear projection), model weights in `stgnn_best.pt` (SHA-256: `68b04504eae6...`).

---

## 2. Authentication & Authorization State
- **Password Hashing:** PBKDF2-HMAC-SHA256 with 100,000 iterations and per-user 16-byte random salt.
- **Tokens:** Custom HS256-signed JWTs with 72-hour default expiration (12 hours for guest).
- **Roles in Database:** `role` column in `users` table. Seeded accounts had arbitrary strings (`commuter`, `logistics_operator`, `patrol_officer`, `guest`). Existing auto-seeding on empty DB will be removed and migrated to explicit `python -m app.seed_demo`.
- **Phase 1 Target:** Strict role normalization to `guest`, `user`, `patrol`, `admin`. Public registration strictly forced to `user` (rejecting/ignoring client `role`). Patrol provisioning restricted to CLI command and admin promotion.
- **Guest Access:** `POST /api/v1/auth/guest` issues signed token with `sub="0"` and `role="guest"`. Must be strictly read-only on all backend write endpoints.

---

## 3. Data Storage & Schema Evolution
- **Database:** SQLite at `data/routewise_local.db`.
- **Migration Strategy:** Lightweight schema initialization via DDL scripts (`CREATE TABLE IF NOT EXISTS ...` with index creation).
- **Existing Tables:**
  - `users`: `id`, `email`, `name`, `password_hash`, `salt`, `role`, `preferred_vehicle`, `created_at`.
- **New Tables to Introduce (Phase 2):**
  - `reports`: UUID primary key, `client_uuid` idempotency key, `reporter_id`, `category`, `description`, `latitude`, `longitude`, `nearest_segment_id`, `photo_path`, `status`, `assigned_to`, `created_at`, `updated_at`, `is_simulated`.
  - `report_status_history`: append-only audit trail (`report_id`, `from_status`, `to_status`, `actor_id`, `actor_role`, `note`, `timestamp`).

---

## 4. Existing API Endpoints & Consumption
- `GET /` & `GET /api/health`: System status, corridor stats, model version.
- `POST /api/v1/auth/register`, `POST /api/v1/auth/login`, `POST /api/v1/auth/guest`, `GET /api/v1/auth/me`, `PUT /api/v1/auth/profile`, `GET /api/v1/auth/demo-accounts`.
- `GET /api/v1/corridor/segments`, `GET /api/v1/corridor/geojson`: 151 NH-44 segment geometries.
- `GET /api/v1/risk`: Retrospective disruption risk scores for observation dates.
- `GET /api/v1/risk/dates`: Catalog of 1,821 historical observation dates.
- `GET /api/v1/journey/places`, `POST /api/v1/journey/plan`: Itinerary and risk profile.
- `GET /api/v1/disruptions`, `GET /api/v1/disruptions/stats`: 99 historical snapped events.
- `POST /api/v1/chat/query`: Domain assistant endpoint.

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
