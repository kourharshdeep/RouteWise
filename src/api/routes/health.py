"""System health check and status endpoint."""
from __future__ import annotations

from datetime import datetime, timezone
from fastapi import APIRouter

from src.api.config import settings
from src.api.schemas.health import HealthCheckResponse
from src.services.risk_service import risk_service

router = APIRouter(tags=["Health"])


@router.get("/health", response_model=HealthCheckResponse)
def get_health() -> HealthCheckResponse:
    """Returns application health, version, model checkpoint hash, and cache status."""
    meta = risk_service.get_metadata() if risk_service.is_available else {}
    model_version = meta.get("model_version", "unknown")
    total_dates = meta.get("total_dates_evaluated", 0)

    return HealthCheckResponse(
        status="ok" if risk_service.is_available else "degraded",
        service=settings.app_name,
        version=settings.app_version,
        model_version=model_version,
        corridor="NH-44 Ramban–Banihal",
        segment_count=151,
        cache_available=risk_service.is_available,
        available_dates_count=total_dates,
        timestamp=datetime.now(timezone.utc).isoformat(),
    )
