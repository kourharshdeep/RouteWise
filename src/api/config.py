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
    db_path: Path = Path(os.getenv("ROUTEWISE_DB_PATH", "data/routewise_local.db"))
    disruptions_path: Path = Path(os.getenv("ROUTEWISE_DISRUPTIONS_PATH", "data/disruption_log_snapped.csv"))
    places_path: Path = Path(os.getenv("ROUTEWISE_PLACES_PATH", "data/place_coordinates.csv"))

    # Security & Authentication
    secret_key: str = os.getenv("ROUTEWISE_SECRET_KEY", "routewise-nh44-ramban-banihal-secure-salt-2026")
    token_expire_hours: int = int(os.getenv("ROUTEWISE_TOKEN_EXPIRE_HOURS", "72"))
    guest_token_expire_hours: int = int(os.getenv("ROUTEWISE_GUEST_EXPIRE_HOURS", "12"))
    demo_patrol_password: str = os.getenv("DEMO_PATROL_PASSWORD", "DemoPatrol2026!")

    # File uploads
    max_upload_bytes: int = int(os.getenv("ROUTEWISE_MAX_UPLOAD_BYTES", str(5 * 1024 * 1024)))  # 5 MB
    uploads_dir: Path = Path(os.getenv("ROUTEWISE_UPLOADS_DIR", "data/uploads"))
    weather_daily_path: Path = Path(os.getenv("ROUTEWISE_WEATHER_PATH", "data/weather_daily_by_segment.csv"))

    # Optional External AI API Key (never exposed to frontend)
    gemini_api_key: str = os.getenv("GEMINI_API_KEY", "")
    openai_api_key: str = os.getenv("OPENAI_API_KEY", "")

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

