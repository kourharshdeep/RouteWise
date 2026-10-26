"""RouteWise API Configuration.

Environment-based configuration without extra third-party dependencies.
"""
from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import List


def _load_env_file() -> None:
    """Zero-dependency .env reader that populates os.environ if present."""
    candidates = [
        Path(".env"),
        Path(__file__).resolve().parent.parent.parent / ".env",
    ]
    for env_path in candidates:
        if env_path.is_file():
            try:
                with open(env_path, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if not line or line.startswith("#") or "=" not in line:
                            continue
                        k, v = line.split("=", 1)
                        k, v = k.strip(), v.strip()
                        if (v.startswith('"') and v.endswith('"')) or (v.startswith("'") and v.endswith("'")):
                            v = v[1:-1]
                        if k and k not in os.environ:
                            os.environ[k] = v
                break
            except Exception:
                pass


_load_env_file()


def _validate_secret_key(key: str | None) -> str:
    """Validates ROUTEWISE_SECRET_KEY according to security requirements."""
    if not key or not key.strip():
        raise RuntimeError(
            "ROUTEWISE_SECRET_KEY environment variable is missing. "
            "RouteWise refuses to start without a valid secret key. "
            "Please configure ROUTEWISE_SECRET_KEY in your environment or .env file (minimum 32 characters)."
        )
    key = key.strip()
    if len(key) < 32:
        raise RuntimeError(
            f"ROUTEWISE_SECRET_KEY is too short ({len(key)} chars; minimum 32 characters required). "
            "Please generate a secure secret key, for example: "
            'python -c "import secrets; print(secrets.token_hex(32))"'
        )
    # Reject known compromised public repository default (checked by SHA-256)
    if hashlib.sha256(key.encode("utf-8")).hexdigest() == "30721de37365e8cb1f367e555813b579550ea30b4c6bec14f6b9156accf20f47":
        raise RuntimeError(
            "ROUTEWISE_SECRET_KEY is set to a compromised public repository default. "
            "RouteWise refuses to start. Please generate a new unique secret key."
        )
    key_lower = key.lower()
    if "change-me" in key_lower or "changeme" in key_lower or "placeholder" in key_lower:
        raise RuntimeError(
            "ROUTEWISE_SECRET_KEY is set to a placeholder value. "
            "RouteWise refuses to start. Please configure a genuine secret key."
        )
    return key


@dataclass(frozen=True)
class Settings:
    """Application settings with environment variable overrides."""

    api_prefix: str = "/api"
    app_name: str = "RouteWise Predictive Disruption API"
    app_version: str = "1.0.0-w8"
    debug: bool = field(default_factory=lambda: os.getenv("ROUTEWISE_DEBUG", "false").lower() == "true")
    host: str = field(default_factory=lambda: os.getenv("ROUTEWISE_HOST", "127.0.0.1"))
    port: int = field(default_factory=lambda: int(os.getenv("ROUTEWISE_PORT", "8000")))

    # File paths
    risk_cache_path: Path = field(default_factory=lambda: Path(os.getenv("ROUTEWISE_CACHE_PATH", "cache/precomputed_risk_cache.json")))
    corridor_graph_path: Path = field(default_factory=lambda: Path(os.getenv("ROUTEWISE_GRAPH_PATH", "nh44_corridor_graph.graphml")))
    static_segments_path: Path = field(default_factory=lambda: Path(os.getenv("ROUTEWISE_STATIC_PATH", "data/segment_static.csv")))
    checkpoint_path: Path = field(default_factory=lambda: Path(os.getenv("ROUTEWISE_CHECKPOINT_PATH", "stgnn_best.pt")))
    db_path: Path = field(default_factory=lambda: Path(os.getenv("ROUTEWISE_DB_PATH", "data/routewise_local.db")))
    disruptions_path: Path = field(default_factory=lambda: Path(os.getenv("ROUTEWISE_DISRUPTIONS_PATH", "data/disruption_log_snapped.csv")))
    places_path: Path = field(default_factory=lambda: Path(os.getenv("ROUTEWISE_PLACES_PATH", "data/place_coordinates.csv")))

    # Security & Authentication (no default secret key; validated at startup)
    secret_key: str = field(default_factory=lambda: _validate_secret_key(os.getenv("ROUTEWISE_SECRET_KEY")))
    token_expire_hours: int = field(default_factory=lambda: int(os.getenv("ROUTEWISE_TOKEN_EXPIRE_HOURS", "72")))
    guest_token_expire_hours: int = field(default_factory=lambda: int(os.getenv("ROUTEWISE_GUEST_EXPIRE_HOURS", "12")))
    demo_patrol_password: str = field(default_factory=lambda: os.getenv("DEMO_PATROL_PASSWORD", ""))
    demo_user_password: str = field(default_factory=lambda: os.getenv("DEMO_USER_PASSWORD", ""))
    demo_mode: bool = field(default_factory=lambda: os.getenv("ROUTEWISE_DEMO_MODE", "false").lower() == "true")

    # File uploads
    max_upload_bytes: int = field(default_factory=lambda: int(os.getenv("ROUTEWISE_MAX_UPLOAD_BYTES", str(5 * 1024 * 1024))))  # 5 MB
    uploads_dir: Path = field(default_factory=lambda: Path(os.getenv("ROUTEWISE_UPLOADS_DIR", "data/uploads")))
    weather_daily_path: Path = field(default_factory=lambda: Path(os.getenv("ROUTEWISE_WEATHER_PATH", "data/weather_daily_by_segment.csv")))

    # Optional External AI API Key (never exposed to frontend)
    gemini_api_key: str = field(default_factory=lambda: os.getenv("GEMINI_API_KEY", ""))
    openai_api_key: str = field(default_factory=lambda: os.getenv("OPENAI_API_KEY", ""))

    # CORS settings
    cors_origins: List[str] = field(
        default_factory=lambda: [
            orig.strip()
            for orig in os.getenv(
                "ROUTEWISE_CORS_ORIGINS",
                "http://localhost:5173,http://127.0.0.1:5173,http://localhost:3000,http://127.0.0.1:8000",
            ).split(",")
            if orig.strip()
        ]
    )


settings = Settings()


