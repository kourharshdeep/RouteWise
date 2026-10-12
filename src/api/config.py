"""RouteWise API Configuration.

Environment-based configuration without extra third-party dependencies.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import List


@dataclass(frozen=True)
class Settings:
    """Application settings with environment variable overrides."""

    api_prefix: str = "/api"
    app_name: str = "RouteWise Predictive Disruption API"
    app_version: str = "1.0.0-w8"
    debug: bool = os.getenv("ROUTEWISE_DEBUG", "false").lower() == "true"
    host: str = os.getenv("ROUTEWISE_HOST", "127.0.0.1")
    port: int = int(os.getenv("ROUTEWISE_PORT", "8000"))

    # File paths
    risk_cache_path: Path = Path(os.getenv("ROUTEWISE_CACHE_PATH", "cache/precomputed_risk_cache.json"))
    corridor_graph_path: Path = Path(os.getenv("ROUTEWISE_GRAPH_PATH", "nh44_corridor_graph.graphml"))
    static_segments_path: Path = Path(os.getenv("ROUTEWISE_STATIC_PATH", "data/segment_static.csv"))
    checkpoint_path: Path = Path(os.getenv("ROUTEWISE_CHECKPOINT_PATH", "stgnn_best.pt"))

    # CORS settings
    cors_origins: List[str] = field(
        default_factory=lambda: [
            "http://localhost:5173",
            "http://127.0.0.1:5173",
            "http://localhost:3000",
            "http://127.0.0.1:8000",
        ]
    )


settings = Settings()
