"""Multi-Objective Routing Algorithm and Corridor Topology Engine.

Implements parameterized Dijkstra / A* pathfinding with configurable risk trade-off:
    cost(e) = travel_time(e) + (lambda_risk * risk_penalty(e))

When lambda_risk = 0.0: produces the fastest route (time-minimizing).
When lambda_risk > 0: penalizes high-risk edges, selecting lower-hazard bypasses if available.

Explicit Topology Note:
    The real NH-44 Ramban–Banihal highway corridor is a single, continuous linear mountain
    artery without parallel highway bypasses within the corridor graph. Consequently, on the
    real corridor, fastest and safest routes follow the identical physical sequence of segments,
    while alternative options are evaluated across observation dates.
"""
from __future__ import annotations

import heapq
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple


@dataclass
class GraphEdge:
    """Directed edge in road network graph."""

    u: str
    v: str
    edge_id: str
    length_m: float
    travel_time_sec: float
    risk_score: float  # [0.0, 1.0]
    is_blocked: bool = False


@dataclass
class RouteResult:
    """Outcome of pathfinding calculation."""

    path_nodes: List[str]
    edge_ids: List[str]
    total_distance_m: float
    total_travel_time_sec: float
    cumulative_risk: float
    max_risk_score: float
    average_risk_score: float
    is_reachable: bool = True
    bottlenecks: List[str] = field(default_factory=list)
    trade_off_explanation: str = ""


class MultiObjectiveRouter:
    """Graph routing engine supporting fastest, safest, and constrained route finding."""

    def __init__(self) -> None:
        self.adjacency: Dict[str, List[GraphEdge]] = {}

    def add_edge(
        self,
        u: str,
        v: str,
        edge_id: str,
        length_m: float,
        travel_time_sec: float,
        risk_score: float,
        is_blocked: bool = False,
    ) -> None:
        """Adds a directed edge to the graph."""
        if u not in self.adjacency:
            self.adjacency[u] = []
        if v not in self.adjacency:
            self.adjacency[v] = []

        edge = GraphEdge(
            u=u,
            v=v,
            edge_id=edge_id,
            length_m=length_m,
            travel_time_sec=travel_time_sec,
            risk_score=max(0.0, min(1.0, risk_score)),
            is_blocked=is_blocked,
        )
        self.adjacency[u].append(edge)

    def find_route(
        self,
        origin: str,
        destination: str,
        lambda_risk: float = 0.0,
        risk_block_threshold: float = 1.0,
    ) -> Optional[RouteResult]:
        """Calculates optimal path from origin to destination using cost = travel_time + lambda * (risk_score * travel_time).
        
        Args:
            origin: Starting node ID.
            destination: Target node ID.
            lambda_risk: Trade-off parameter (0.0 = purely fastest, 10.0+ = strongly safest).
            risk_block_threshold: Risk score at or above which an edge is considered impassable.
            
        Returns:
            RouteResult if reachable, else None.
        """
        if origin not in self.adjacency or destination not in self.adjacency:
            return None

        if origin == destination:
            return RouteResult(
                path_nodes=[origin],
                edge_ids=[],
                total_distance_m=0.0,
                total_travel_time_sec=0.0,
                cumulative_risk=0.0,
                max_risk_score=0.0,
                average_risk_score=0.0,
                is_reachable=True,
                trade_off_explanation="Origin and destination are identical.",
            )

        # Priority queue stores tuples: (cumulative_cost, cumulative_time, tie_breaker_count, current_node, path_nodes, path_edges)
        counter = 0
        heap: List[Tuple[float, float, int, str, List[str], List[GraphEdge]]] = []
        heapq.heappush(heap, (0.0, 0.0, counter, origin, [origin], []))

        best_cost: Dict[str, float] = {origin: 0.0}

        while heap:
            current_cost, current_time, _, u, path_nodes, path_edges = heapq.heappop(heap)

            if u == destination:
                total_dist = sum(e.length_m for e in path_edges)
                total_time = sum(e.travel_time_sec for e in path_edges)
                scores = [e.risk_score for e in path_edges]
                max_s = max(scores) if scores else 0.0
                avg_s = sum(scores) / len(scores) if scores else 0.0
                cum_risk = sum(e.risk_score * e.travel_time_sec for e in path_edges)
                edge_ids = [e.edge_id for e in path_edges]
                bottlenecks = [e.edge_id for e in path_edges if e.risk_score >= 0.35]

                explanation = (
                    f"Selected route via {'fastest' if lambda_risk == 0.0 else 'safest'} priority "
                    f"(lambda={lambda_risk:.1f}): total travel time {total_time:.1f}s, "
                    f"average risk {avg_s:.3f}, max hazard score {max_s:.3f}."
                )

                return RouteResult(
                    path_nodes=path_nodes,
                    edge_ids=edge_ids,
                    total_distance_m=round(total_dist, 1),
                    total_travel_time_sec=round(total_time, 1),
                    cumulative_risk=round(cum_risk, 2),
                    max_risk_score=round(max_s, 4),
                    average_risk_score=round(avg_s, 4),
                    is_reachable=True,
                    bottlenecks=bottlenecks,
                    trade_off_explanation=explanation,
                )

            if current_cost > best_cost.get(u, float("inf")):
                continue

            for edge in self.adjacency.get(u, []):
                # Check blocked edge or excessive hazard threshold
                if edge.is_blocked or edge.risk_score >= risk_block_threshold:
                    continue

                # Multi-objective edge cost: travel time + risk penalty weighted by lambda
                # Using risk_score * travel_time gives exposure over duration of transit
                edge_cost = edge.travel_time_sec + (lambda_risk * edge.risk_score * edge.travel_time_sec)
                new_cost = current_cost + edge_cost
                new_time = current_time + edge.travel_time_sec
                v = edge.v

                if new_cost < best_cost.get(v, float("inf")):
                    best_cost[v] = new_cost
                    counter += 1
                    heapq.heappush(
                        heap,
                        (
                            new_cost,
                            new_time,
                            counter,
                            v,
                            path_nodes + [v],
                            path_edges + [edge],
                        ),
                    )

        return None
