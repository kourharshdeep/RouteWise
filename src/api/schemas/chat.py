"""Conversational AI Assistant schemas."""
from __future__ import annotations

from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class ChatMessage(BaseModel):
    """Single message in a conversational thread."""

    role: str = Field(..., description="'user', 'assistant', or 'system'")
    content: str = Field(..., description="Message text content")
    timestamp: Optional[str] = None


class ChatContext(BaseModel):
    """Application state context passed to the assistant."""

    selected_date: Optional[str] = "2023-07-09"
    vehicle_type: Optional[str] = "Car"
    origin: Optional[str] = "Ramban"
    destination: Optional[str] = "Banihal"
    selected_segment_id: Optional[str] = None


class ChatQueryRequest(BaseModel):
    """User query payload sent to the assistant."""

    message: str = Field(..., min_length=1, description="User prompt or question")
    history: List[ChatMessage] = Field(default_factory=list, description="Prior conversation messages")
    context: Optional[ChatContext] = None


class ChatQueryResponse(BaseModel):
    """Assistant reply with suggested followups and source indicator."""

    reply: str
    suggested_followups: List[str]
    source_engine: str
    is_live_llm: bool
    context_applied: Dict[str, Any]
