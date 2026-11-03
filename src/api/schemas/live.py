"""Pydantic schemas for RouteWise Live Risk and Operational Status endpoints."""
from __future__ import annotations

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class LiveStatusResponse(BaseModel):
    mode: str = Field(..., description="Operational live mode: 'off' | 'replay' | 'live'")
    experimental: bool = Field(True, description="Always true for live real-time outputs")
    provider: str = Field(..., description="Active atmospheric provider")
    latest_fetch: Optional[str] = Field(None, description="ISO timestamp of most recent weather fetch")
    data_age_hours: Optional[float] = Field(None, description="Elapsed hours since latest fetch")
    latest_weather_date: Optional[str] = Field(None, description="Latest observation date (YYYY-MM-DD)")
    latest_risk_as_of: Optional[str] = Field(None, description="Most recent risk evaluation target date")
    total_segments: int = Field(..., description="Total corridor segments evaluated")
    unknown_count: int = Field(..., description="Count of segments with UNKNOWN tier (missing/stale)")
    stale_count: int = Field(..., description="Count of segments flagged stale")
    checkpoint_sha256: str = Field(..., description="SHA-256 checksum of model weights")
    validation_summary: Dict[str, Any] = Field(..., description="Meteorological distribution shift summary")


class LiveRiskSegmentItem(BaseModel):
    segment_id: str
    risk_score: Optional[float] = Field(None, description="Advisory relative-risk index in [0, 1]")
    risk_tier: str = Field(..., description="Risk tier: 'Low' | 'Medium' | 'High' | 'UNKNOWN'")
    status: str = Field(..., description="Evaluation status: 'OK' | 'MISSING_DATA' | 'STALE_DATA'")
    is_stale: bool = Field(..., description="True if newest observation > 24 hours old")
    model_version: str
    checkpoint_sha256: str
    weather_window_end: str
    computed_at: str


class LiveRiskResponse(BaseModel):
    as_of: Optional[str] = Field(None, description="Evaluation target date (YYYY-MM-DD)")
    computed_at: Optional[str] = Field(None, description="Timestamp of inference execution")
    experimental: bool = Field(True, description="Always true; live predictions are not validated")
    disclaimer: str = Field(..., description="Honest framing disclaimer regarding distribution shift")
    model_version: str
    checkpoint_sha256: str
    summary: Dict[str, int] = Field(..., description="Tier counts: Low, Medium, High, UNKNOWN")
    segments: List[LiveRiskSegmentItem] = Field(..., description="Predictions for all 151 segments")


class LiveRiskChangeItem(BaseModel):
    segment_id: str
    as_of: str
    risk_score: Optional[float]
    risk_tier: str
    status: str
    is_stale: bool
    computed_at: str


class LiveRiskChangesResponse(BaseModel):
    since: Optional[str]
    count: int
    changes: List[LiveRiskChangeItem]
