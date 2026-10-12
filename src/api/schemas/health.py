"""Health check response schema."""
from __future__ import annotations

from pydantic import BaseModel, Field


class HealthCheckResponse(BaseModel):
    """System health check and runtime metadata."""

    status: str = Field(..., description="Service status ('ok' or 'degraded')")
    service: str = Field(..., description="Service identifier")
    version: str = Field(..., description="Application version")
    model_version: str = Field(..., description="Checkpoint SHA-256 hash prefix")
    corridor: str = Field(default="NH-44 Ramban–Banihal", description="Operational highway stretch")
    segment_count: int = Field(default=151, description="Number of modeled road segments")
    cache_available: bool = Field(..., description="Whether precomputed risk cache is loaded")
    available_dates_count: int = Field(..., description="Total observation dates in cache")
    timestamp: str = Field(..., description="ISO 8601 UTC timestamp")
