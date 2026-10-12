"""Risk forecast request and response schemas."""
from __future__ import annotations

from typing import Dict, List, Optional
from pydantic import BaseModel, Field


class SegmentRiskItem(BaseModel):
    """Risk prediction item for a single highway segment."""

    segment_id: str = Field(..., description="Unique graph edge identifier")
    risk_score: Optional[float] = Field(None, description="Advisory risk score in [0.0, 1.0], or null if missing/stale")
    risk_tier: str = Field(..., description="Semantic tier ('Low', 'Medium', 'High', or 'UNKNOWN')")
    status: str = Field(..., description="Evaluation status ('OK', 'MISSING_DATA', 'STALE_DATA')")
    is_stale: bool = Field(default=False, description="Whether input weather data exceeded 24h freshness limit")


class RiskSummary(BaseModel):
    """Aggregated risk breakdown across the corridor."""

    total_segments: int = Field(default=151, description="Total corridor segments")
    high_risk_count: int = Field(default=0, description="Segments with score >= 0.35")
    medium_risk_count: int = Field(default=0, description="Segments with 0.10 <= score < 0.35")
    low_risk_count: int = Field(default=0, description="Segments with score < 0.10")
    unknown_count: int = Field(default=0, description="Segments with missing or stale inputs")


class RiskMetadata(BaseModel):
    """Metadata describing the data source, model, and operational limitations."""

    dataset_type: str = Field(default="retrospective_historical_backtest")
    meteorological_source: str = Field(default="ERA5-Land reanalysis via Copernicus CDS")
    is_live_operational_forecast: bool = Field(default=False)
    prediction_horizon_hours: int = Field(default=24)
    model_version: str = Field(...)
    thresholds: Dict[str, float] = Field(...)
    advisory_notice: str = Field(
        default="RouteWise risk scores are advisory ranking estimates for decision support. "
        "They do not guarantee road openness or safety."
    )
    requested_date: str = Field(..., description="Requested evaluation date (YYYY-MM-DD)")
    generated_at: str = Field(..., description="Cache generation timestamp")


class CorridorRiskResponse(BaseModel):
    """Complete corridor risk forecast response."""

    metadata: RiskMetadata
    summary: RiskSummary
    segments: List[SegmentRiskItem]


class AvailableDatesResponse(BaseModel):
    """Date boundaries available in the historical reanalysis cache."""

    start_date: str
    end_date: str
    total_dates: int
    sample_dates: List[str]
    description: str = Field(
        default="Retrospective historical observation dates supported by precomputed risk cache."
    )
