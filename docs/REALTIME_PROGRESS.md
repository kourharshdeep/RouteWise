# RouteWise — Real-Time Intelligence Progress

This file tracks the status, phase specifications, and verification milestones for the Real-Time Intelligence and Operational Routing Phase (Tasks 1 through 4) on branch `feature/realtime-intelligence`.

---

## 1. Core Development Phases & Milestones

| Task / Step | Description | Status | Commit / Reference |
|---|---|:---:|---|
| **Step 0** | Safety setup and live mode configuration (`ROUTEWISE_LIVE_MODE=off\|replay\|live`) | **COMPLETED** | `f6637e5` |
| **Step 1** | Weather storage (`routewise_live.db`) and historical replay provider | **COMPLETED** | `6715b71` |
| **Step 2** | Open-Meteo clustering provider (22 centroids) and atmospheric distribution shift validation | **COMPLETED** | `9923bef` |
| **Step 3** | Live risk service, 7-day rolling window inference wrapping ST-GNN, and REST endpoints | **COMPLETED** | `1d481e9` |
| **Step 4** | Hazard event operational status overlay (`CLOSED`, `RESTRICTED`, `UNKNOWN`, `CAUTION`, `OPEN`) | **COMPLETED** | `f528335` |
| **Step 5** | Live dashboard updates, Server-Sent Events (`/api/v1/live/stream`), and polling fallback | **COMPLETED** | `d9e41e5` |
| **Step 6** | Dynamic multi-objective corridor routing (`HOLD`, `DELAY`, `PROCEED_WITH_CAUTION`, `PROCEED`) | **COMPLETED** | `2e69d8e` |
| **Step 7** | In-app alerts, 1-hour de-duplication cooldown, patrol acknowledgement, and storm scenario | **COMPLETED** | `425ae9f` |
| **Step 8** | Step-by-step verification and baseline closure | **COMPLETED** | `57bd323` |
| **Tasks 2–2d** | Journey planner speed-up (2.5x–23x faster), read-time staleness, stale-alert metadata, off-mode 409 guard | **COMPLETED** | `b032a00` |
| **Task 3** | Current-date live risk, strict UTC window semantics (`weather_window_end = yesterday_utc`), source isolation | **COMPLETED** | `1b0d5a3` |
| **Tasks 3b–3c** | SSE reconnect with full-jitter exponential backoff, polling fallback, React ErrorBoundary, mode-aware planner, SSR render smoke tests | **COMPLETED** | `15d6ee7` |
| **Task 4** | Incident deduplication architecture, fail-closed DB guard, category fallback, verified `last_reported_at`, non-zero route wording, live date substitution | **COMPLETED** | `5fe7deb` |

---

## 2. Summary of Task 4 Hardening & Incident Intelligence

1. **Additive Schema Migration:**
   - `reports` table: added `duplicate_of` (linking duplicate reports to primary report) and `hazard_event_id` (linking to generated/merged active hazard).
   - `hazard_event` table: added `report_count` (total linked reports) and `last_reported_at` (timestamp of most recent verified report).
2. **Fail-Closed Protected Database Guard:**
   - Implemented `_is_protected_db(path)` in `src/services/report_service.py` to prevent any test or runtime mutation of `data/routewise_local.db`. Resolves canonical path and fails closed (treating path as protected if resolution raises an exception).
3. **Category Presets & Fallback Normalization:**
   - Preset categories (`landslide`, `shooting_stones`, `flooding`, `road_damage`) map directly to distinct hazard types.
   - Non-preset report categories (`other`, `snow_or_ice`, `single_lane_or_obstruction`) fall back to `road_damage` in accordance with `VALID_PRESETS`.
   - Preset categories on the same segment create independent hazard events. Fallback categories merge into an existing active road-damage event as duplicates.
4. **Dual Timestamp Deduplication Window:**
   - Active event matching evaluates: `(created_at >= :dedup_limit OR (last_reported_at IS NOT NULL AND last_reported_at >= :dedup_limit))` within the 24-hour window.
5. **Verified-Only Lifecycle Extension:**
   - `last_reported_at` updates and extends the deduplication window only when a corroborating report is transitioned to `verified` by a patrol officer or admin. Unverified or guest submissions do not extend event lifecycles.
6. **Primary vs. Duplicate Rejection Policies:**
   - Rejecting the primary report closes the associated hazard event.
   - Rejecting a duplicate report unlinks that report while leaving the active hazard event open.
7. **Accurate Routing Reason Wording:**
   - Eliminated zero-count citations (e.g. "blocked by 0 closed segments"). Accurately distinguishes physical road closures, stale telemetry (>24h), unmonitored segments, high risk, and clear corridor baseline.
8. **Live Date Substitution UI Notice:**
   - When a historical date is queried in live mode without live telemetry, the planner evaluates the latest available live date, setting `date_substituted=True`, `requested_date`, and `actual_date` with an explanatory notification.

---

## 3. Verified Automated Test Suite Status

- **Backend Test Suite:**
  - `ROUTEWISE_LIVE_MODE="off"`: **206 passed**
  - `ROUTEWISE_LIVE_MODE="replay"`: **206 passed**
  - `ROUTEWISE_LIVE_MODE="live"`: **206 passed**
- **Incident Deduplication Suite (`tests/test_incident_deduplication.py`):** **34 passed**
- **Historical Golden Tests (`tests/test_journey_golden.py`):** **6 passed**
- **Frontend Unit Suite (`npm --prefix frontend test`):** **49 passed** (14 suites)
- **Frontend Production Build (`npm --prefix frontend run build`):** **Succeeded** (Vite v6.4.4)
- **Protected Assets Integrity:** SHA-256 verified for `stgnn_best.pt`, `data/routewise_local.db`, and `data/runtime/routewise_live.db`.
