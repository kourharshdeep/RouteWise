# RouteWise 2.0 — Journey Planning Performance Notes

**Date:** 2026-11-09  
**Branch:** `feature/realtime-intelligence`  
**Measurement Tool:** `scripts/benchmark_journey.py` (cProfile + `time.perf_counter`, 10 repetitions)

---

## 1. Before vs After Optimization Summary

| Operation / Metric | Baseline Before | Optimized After | Change / Speedup |
|---|---|---|---|
| **Live Plan Journey (Cold Start)** | 238.90 ms | 10.08 ms | **23.7x faster** (no network/model/bootstrap) |
| **Live Plan Journey (Warm Median)** | 18.38 ms | 7.44 ms | **2.5x faster** (well under 500 ms target) |
| **Live Plan Journey (Warm P95)** | 22.77 ms | 8.27 ms | **2.8x faster** |
| **Historical: Ramban → Banihal (Median)** | 1.83 ms | 0.97 ms | **1.9x faster** (sub-millisecond) |
| **Historical: Banihal → Ramban (Median)** | 1.46 ms | 0.79 ms | **1.8x faster** (sub-millisecond) |
| `live_risk_service.get_latest_live_risk()` | 5.65 ms | 0.94 ms | **6.0x faster** |
| `hazard_event_service.get_active_events_by_segment_map()` | 2.49 ms | 0.00 ms | **Instant** (in-memory cached) |
| Route graph build (75 edges) | 0.079 ms | 0.064 ms | 1.2x faster |
| Router runs (baseline + risk-aware) | 0.171 ms | 0.130 ms | 1.3x faster |
| SQLite `execute` calls (10 live requests) | 570 calls | 30 calls | **94.7% reduction** in DB queries |

---

## 2. Evaluation of Audit Hypotheses

| Audit Hypothesis | Status | Measured Reality & Resolution |
|---|---|---|
| **1. Repeated GeoJSON parsing** | **Partially Confirmed** | Cold-start GeoJSON load/parse took 117.95 ms. In warm mode, `corridor_service._geojson_cache` avoided file I/O, but `journey_service` rebuilt `features_by_id = {f.id: f for f in geojson.features}` dictionary and re-scanned coordinates with `math.hypot` on every single request. Precomputed static spatial and attribute lookup maps (`_places_by_id`, `_place_to_sorted_idx`, `_segment_props`) eliminated repeated parsing and Euclidean scans entirely. |
| **2. Graph construction** | **Rejected** | Graph construction takes 0.064 ms (64 microseconds) for 75 edges. It was never a bottleneck (<0.5% of request time). |
| **3. Router pathfinding** | **Rejected** | Dual MultiObjectiveRouter execution (baseline + risk-aware) takes 0.130 ms total. It was never a bottleneck (<1% of request time). |
| **4. Status aggregation & SQLite queries** | **Confirmed** | Over 570 SQLite `execute` calls across 10 requests previously. In particular, `live_status = live_risk_service.get_live_status()` took ~6.1 ms per request (40% of total warm request time) to execute 5 queries whose return value was **never used** in `journey_service.py`. Removing the unused query, caching active events with invalidation hooks, guarding `init_db()` against repeated DDL checks, and adding an index on `live_risk(as_of, segment_id)` cut database operations by 94.7%. |
| **5. On-the-fly model inference / weather fetching** | **Confirmed (Critical)** | Code inspection of `live_risk_service.get_latest_live_risk()` lines 395–404 revealed that if `live_risk` was empty, `self.compute_live_risk()` was invoked synchronously on-the-fly. This ran PyTorch neural network inference (`predict_corridor`) and Open-Meteo weather reads inside the user request path. Removed this auto-computation: the planner now strictly reads stored `live_risk` and returns the honest fail-safe `NO_DATA` / `UNKNOWN` response when data is missing or uncomputed, leaving data population strictly to the scheduler, scenario player, and replay runner. |

---

## 3. Post-Optimization cProfile Breakdown (Live `plan_journey`)

```text
         49721 function calls in 0.062 seconds

   Ordered by: cumulative time
   List reduced from 82 to 15 due to restriction <15>

   ncalls  tottime  percall  cumtime  percall filename:lineno(function)
       10    0.005    0.001    0.062    0.006 src/services/journey_service.py:253(plan_journey)
      750    0.001    0.000    0.029    0.000 src/services/routing_engine.py:57(add_edge)
      750    0.027    0.000    0.027    0.000 {built-in method builtins.min}
       10    0.004    0.000    0.018    0.002 src/services/live_risk_service.py:403(get_latest_live_risk)
       10    0.000    0.000    0.011    0.001 src/services/live_risk_service.py:87(_get_connection)
       30    0.006    0.000    0.006    0.000 {method 'execute' of 'sqlite3.Connection' objects}
       20    0.003    0.000    0.005    0.000 src/services/routing_engine.py:84(find_route)
       10    0.000    0.000    0.003    0.000 Lib/pathlib.py:1111(mkdir)
       10    0.003    0.000    0.003    0.000 {built-in method _sqlite3.connect}
     1510    0.001    0.000    0.002    0.000 src/services/hazard_event_service.py:438(derive_operational_status)
     3040    0.001    0.000    0.002    0.000 {built-in method builtins.any}
       10    0.002    0.000    0.002    0.000 {built-in method nt.mkdir}
      790    0.000    0.000    0.002    0.000 pydantic/main.py:270(__init__)
    16690    0.001    0.000    0.001    0.000 {method 'get' of 'dict' objects}
      790    0.001    0.000    0.001    0.000 {method 'validate_python' of 'pydantic_core._pydantic_core.SchemaValidator' objects}
```


---

## 4. Cache Architecture & Single-Process Assumptions

### 4.1 In-Memory Caching Architecture
To satisfy the <500 ms p95 response time requirement without network or neural network overhead in the request path, RouteWise uses localized in-memory caches:

1. **Static Spatial & Corridor Properties (`journey_service.py`)**:
   - `_places_by_id`, `_places_by_name`: O(1) dictionary lookups for landmark resolution.
   - `_place_to_sorted_idx`: O(1) index lookup in the ordered 151-segment sequence, with defensive geometric fallback.
   - `_segment_props`: O(1) lookup for segment physical properties (`length_m`, `slope`, `elevation_m`, `highway`), eliminating repeated GeoJSON dictionary iteration.
2. **Active Hazard Events Cache (`hazard_event_service.py`)**:
   - `_active_events_cache`: Stores the list of active hazard events in memory.
   - `_cache_earliest_expires_at`: Tracks the earliest ISO expiration timestamp among active events.
3. **Live Risk Rows Cache (`live_risk_service.py`)**:
   - `_risk_rows_cache`: Caches the 151 live risk rows for `(db_path, target_as_of)` to avoid redundant deserialization within the same polling window.
4. **Resilient DDL Init Cache (`_initialized_dbs`)**:
   - Skips repetitive `CREATE TABLE IF NOT EXISTS` and index statements across requests, while verifying table presence in `sqlite_master` to ensure immediate recreation if the runtime SQLite file is deleted or truncated.

### 4.2 Invalidation Triggers

| Cache Component | Invalidation Trigger | Action |
|---|---|---|
| **Active Hazards** (`_active_events_cache`) | `simulate_event()` | Calls `_broadcast_event_change("simulate")` -> `invalidate_cache()` |
| **Active Hazards** (`_active_events_cache`) | `clear_all_simulated_events()` | Calls `_broadcast_event_change("clear_simulated")` -> `invalidate_cache()` |
| **Active Hazards** (`_active_events_cache`) | `on_report_status_change()` | Calls `_broadcast_event_change(...)` on verify/resolve/reject -> `invalidate_cache()` |
| **Active Hazards** (`_active_events_cache`) | Passage of time (`now >= _cache_earliest_expires_at`) | Auto-expires overdue rows in SQLite via `expire_active_events()` and resets `_active_events_cache = None` with **zero database mutation required** beforehand |
| **Live Risk Rows** (`_risk_rows_cache`) | `compute_live_risk()` | Calls `invalidate_cache()` upon committing new predictions to SQLite |
| **Database Schema** (`_initialized_dbs`) | Disk deletion / truncation | Bypasses cache when `not db_path.is_file()` or SQLite table is missing from `sqlite_master` |

### 4.3 Single-Process Assumption & Multi-Worker Production Considerations
- **Current Operational Scope**: The current in-memory cache implementation explicitly assumes a **single-process runtime** (e.g. single Uvicorn ASGI process, development server, or test harness). In this model, in-memory references provide instantaneous consistency across all endpoints (`/api/v1/live/risk`, `POST /api/v1/journey/plan`, `/api/v1/live/stream`).
- **Horizontal Scaling Caveat**: If the backend is scaled horizontally to multiple worker processes (e.g. `gunicorn -w 4 -k uvicorn.workers.UvicornWorker` or multi-container Kubernetes pods):
  - Invalidation calls in Worker A (such as an operator simulating a hazard event) will clear Worker A's in-memory cache, but Worker B's in-memory cache would remain stale until its earliest expiration timestamp passes.
  - For multi-process deployments, in-memory caches must be paired with an inter-process invalidation bus (e.g., Redis Pub/Sub, SQLite WAL write counter / schema PRAGMA checking, or database change notifications).
