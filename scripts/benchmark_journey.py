"""Benchmark journey planning performance across historical and live modes.

Measures:
1. Historical plan_journey (Ramban -> Banihal, Banihal -> Ramban)
2. Live plan_journey (cold and warm)
3. Isolated component timings:
   - GeoJSON load/parse
   - Live risk read path
   - Corridor status aggregation (events & operational status)
   - Route graph build
   - Router pathfinding runs (baseline + risk-aware)
4. cProfile top-15 functions by cumulative time
"""
from __future__ import annotations

import cProfile
import io
import pstats
import sys
import time
from pathlib import Path
from typing import Callable, List

# Ensure repository root is on path
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.api.schemas.journey import JourneyPlanRequest
from src.services.corridor_service import corridor_service
from src.services.hazard_event_service import hazard_event_service
from src.services.journey_service import journey_service
from src.services.live_risk_service import live_risk_service
from src.services.routing_engine import MultiObjectiveRouter


def measure_stats(fn: Callable[[], None], n: int = 10) -> tuple[float, float, float]:
    """Runs fn n times, returning (min, median, p95) in milliseconds."""
    durations: List[float] = []
    for _ in range(n):
        t0 = time.perf_counter()
        fn()
        t1 = time.perf_counter()
        durations.append((t1 - t0) * 1000.0)

    durations.sort()
    min_val = durations[0]
    median_val = durations[n // 2] if n % 2 != 0 else (durations[n // 2 - 1] + durations[n // 2]) / 2.0
    p95_idx = int(round(0.95 * (n - 1)))
    p95_val = durations[p95_idx]
    return min_val, median_val, p95_val


def run_benchmark():
    print("=" * 70)
    print("RouteWise Journey Planning Benchmark (Pre-Optimization)")
    print("=" * 70)

    # 1. Measure GeoJSON load alone (cold)
    corridor_service._geojson_cache = None
    t0 = time.perf_counter()
    geojson = corridor_service.get_corridor_geojson()
    t_cold_geojson = (time.perf_counter() - t0) * 1000.0
    print(f"[*] Corridor GeoJSON Load/Parse (Cold): {t_cold_geojson:.2f} ms")

    # Measure GeoJSON load warm
    min_gj, med_gj, p95_gj = measure_stats(lambda: corridor_service.get_corridor_geojson(), n=10)
    print(f"[*] Corridor GeoJSON Load (Warm Cache): min={min_gj:.3f}ms, med={med_gj:.3f}ms, p95={p95_gj:.3f}ms")

    # 2. Historical Mode (Ramban -> Banihal)
    req_hist_fwd = JourneyPlanRequest(
        origin="Ramban Gateway",
        destination="Banihal Gateway",
        date="2023-07-09",
        mode="historical",
        vehicle_type="Car",
    )
    min_hf, med_hf, p95_hf = measure_stats(lambda: journey_service.plan_journey(req_hist_fwd), n=10)
    print(f"[*] Historical (Ramban -> Banihal): min={min_hf:.2f}ms, med={med_hf:.2f}ms, p95={p95_hf:.2f}ms")

    # Historical Mode (Banihal -> Ramban)
    req_hist_rev = JourneyPlanRequest(
        origin="Banihal Gateway",
        destination="Ramban Gateway",
        date="2023-07-09",
        mode="historical",
        vehicle_type="Car",
    )
    min_hr, med_hr, p95_hr = measure_stats(lambda: journey_service.plan_journey(req_hist_rev), n=10)
    print(f"[*] Historical (Banihal -> Ramban): min={min_hr:.2f}ms, med={med_hr:.2f}ms, p95={p95_hr:.2f}ms")

    # 3. Live Mode (Cold & Warm)
    req_live = JourneyPlanRequest(
        origin="Ramban Gateway",
        destination="Banihal Gateway",
        mode="live",
        vehicle_type="Car",
    )

    # Measure cold live call (clearing GeoJSON cache first to simulate cold start)
    corridor_service._geojson_cache = None
    t0 = time.perf_counter()
    journey_service.plan_journey(req_live)
    t_cold_live = (time.perf_counter() - t0) * 1000.0
    print(f"[*] Live plan_journey (Cold start): {t_cold_live:.2f} ms")

    min_lw, med_lw, p95_lw = measure_stats(lambda: journey_service.plan_journey(req_live), n=10)
    print(f"[*] Live plan_journey (Warm): min={min_lw:.2f}ms, med={med_lw:.2f}ms, p95={p95_lw:.2f}ms")

    # 4. Component-level breakdown (isolated)
    # 4a. Live risk read path alone
    min_lr, med_lr, p95_lr = measure_stats(lambda: live_risk_service.get_latest_live_risk(), n=10)
    print(f"[*] Component: live_risk_service.get_latest_live_risk(): min={min_lr:.2f}ms, med={med_lr:.2f}ms, p95={p95_lr:.2f}ms")

    # 4b. live_status call alone
    min_ls, med_ls, p95_ls = measure_stats(lambda: live_risk_service.get_live_status(), n=10)
    print(f"[*] Component: live_risk_service.get_live_status(): min={min_ls:.2f}ms, med={med_ls:.2f}ms, p95={p95_ls:.2f}ms")

    # 4c. Hazard events map alone
    min_he, med_he, p95_he = measure_stats(lambda: hazard_event_service.get_active_events_by_segment_map(), n=10)
    print(f"[*] Component: hazard_event_service.get_active_events_by_segment_map(): min={min_he:.2f}ms, med={med_he:.2f}ms, p95={p95_he:.2f}ms")

    # 4d. Graph build alone
    features_by_id = {f.id: f for f in geojson.features}
    selected_segments = journey_service._sorted_segment_ids[:75]

    def build_test_graph():
        r = MultiObjectiveRouter()
        for i, sid in enumerate(selected_segments):
            r.add_edge(f"node_{i}", f"node_{i+1}", sid, 200.0, 16.0, 0.1, False)
        return r

    min_gb, med_gb, p95_gb = measure_stats(build_test_graph, n=10)
    print(f"[*] Component: Route graph build (75 edges): min={min_gb:.3f}ms, med={med_gb:.3f}ms, p95={p95_gb:.3f}ms")

    # 4e. Router run(s) alone
    test_router = build_test_graph()

    def run_router():
        test_router.find_route("node_0", "node_75", lambda_risk=0.0)
        test_router.find_route("node_0", "node_75", lambda_risk=5.0)

    min_rr, med_rr, p95_rr = measure_stats(run_router, n=10)
    print(f"[*] Component: Router runs (baseline + risk-aware): min={min_rr:.3f}ms, med={med_rr:.3f}ms, p95={p95_rr:.3f}ms")

    # 5. cProfile on live plan_journey
    print("\n" + "=" * 70)
    print("cProfile: Top 15 Functions by Cumulative Time (Live plan_journey)")
    print("=" * 70)
    pr = cProfile.Profile()
    pr.enable()
    for _ in range(10):
        journey_service.plan_journey(req_live)
    pr.disable()

    s = io.StringIO()
    ps = pstats.Stats(pr, stream=s).sort_stats(pstats.SortKey.CUMULATIVE)
    ps.print_stats(15)
    print(s.getvalue())


if __name__ == "__main__":
    run_benchmark()

