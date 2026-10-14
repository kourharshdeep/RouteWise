"""Unit tests for multi-objective routing algorithm on synthetic topologies."""
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import pytest
from src.services.routing_engine import MultiObjectiveRouter


@pytest.fixture
def diamond_graph() -> MultiObjectiveRouter:
    r"""Creates a synthetic multi-path diamond graph:
        
             B (fast, high risk)
           /   \
         A       D
           \   /
             C (slow, low risk)
    """
    router = MultiObjectiveRouter()
    # Path 1: A -> B -> D (Travel time = 10s + 10s = 20s, Risk = 0.8)
    router.add_edge("A", "B", "e_ab", length_m=500, travel_time_sec=10.0, risk_score=0.8)
    router.add_edge("B", "D", "e_bd", length_m=500, travel_time_sec=10.0, risk_score=0.8)

    # Path 2: A -> C -> D (Travel time = 25s + 25s = 50s, Risk = 0.05)
    router.add_edge("A", "C", "e_ac", length_m=1200, travel_time_sec=25.0, risk_score=0.05)
    router.add_edge("C", "D", "e_cd", length_m=1200, travel_time_sec=25.0, risk_score=0.05)

    return router


def test_fastest_route_selection(diamond_graph):
    """When lambda=0, router must choose fastest path (A -> B -> D)."""
    res = diamond_graph.find_route("A", "D", lambda_risk=0.0)
    assert res is not None
    assert res.path_nodes == ["A", "B", "D"]
    assert res.total_travel_time_sec == 20.0
    assert res.average_risk_score == 0.8


def test_safest_route_selection(diamond_graph):
    """When lambda is high, router penalizes the high hazard path and selects A -> C -> D."""
    res = diamond_graph.find_route("A", "D", lambda_risk=5.0)
    assert res is not None
    assert res.path_nodes == ["A", "C", "D"]
    assert res.total_travel_time_sec == 50.0
    assert res.average_risk_score == 0.05


def test_blocked_edge_divergence(diamond_graph):
    """When fastest edge is blocked, router automatically diverts to the open alternative."""
    blocked_graph = MultiObjectiveRouter()
    # Path 1 blocked at B->D
    blocked_graph.add_edge("A", "B", "e_ab", length_m=500, travel_time_sec=10.0, risk_score=0.1)
    blocked_graph.add_edge("B", "D", "e_bd", length_m=500, travel_time_sec=10.0, risk_score=0.1, is_blocked=True)

    # Path 2 open
    blocked_graph.add_edge("A", "C", "e_ac", length_m=800, travel_time_sec=30.0, risk_score=0.1)
    blocked_graph.add_edge("C", "D", "e_cd", length_m=800, travel_time_sec=30.0, risk_score=0.1)

    res = blocked_graph.find_route("A", "D", lambda_risk=0.0)
    assert res is not None
    assert res.path_nodes == ["A", "C", "D"]


def test_risk_threshold_exclusion(diamond_graph):
    """Edges with risk >= threshold are treated as impassable."""
    # Threshold 0.5 excludes Path 1 (risk 0.8) even with lambda=0
    res = diamond_graph.find_route("A", "D", lambda_risk=0.0, risk_block_threshold=0.5)
    assert res is not None
    assert res.path_nodes == ["A", "C", "D"]


def test_unreachable_destination():
    """Returns None when destination cannot be reached."""
    router = MultiObjectiveRouter()
    router.add_edge("A", "B", "e_ab", length_m=100, travel_time_sec=10.0, risk_score=0.1)
    router.add_edge("C", "D", "e_cd", length_m=100, travel_time_sec=10.0, risk_score=0.1)

    res = router.find_route("A", "D")
    assert res is None


def test_linear_corridor_honesty():
    """Simulates a single linear corridor (like Ramban-Banihal).
    Fastest and safest paths are identical because no alternative topology exists.
    """
    corridor = MultiObjectiveRouter()
    corridor.add_edge("Ramban", "Chanderkot", "seg_1", length_m=5000, travel_time_sec=300, risk_score=0.2)
    corridor.add_edge("Chanderkot", "Ramsu", "seg_2", length_m=12000, travel_time_sec=720, risk_score=0.6)
    corridor.add_edge("Ramsu", "Banihal", "seg_3", length_m=8000, travel_time_sec=480, risk_score=0.1)

    fastest = corridor.find_route("Ramban", "Banihal", lambda_risk=0.0)
    safest = corridor.find_route("Ramban", "Banihal", lambda_risk=10.0)

    assert fastest is not None and safest is not None
    assert fastest.path_nodes == safest.path_nodes == ["Ramban", "Chanderkot", "Ramsu", "Banihal"]
    assert fastest.total_distance_m == safest.total_distance_m == 25000.0
    assert "seg_2" in fastest.bottlenecks
