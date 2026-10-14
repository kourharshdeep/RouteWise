"""Conversational AI Assistant API routes."""
from __future__ import annotations

from fastapi import APIRouter

from src.api.schemas.chat import ChatQueryRequest, ChatQueryResponse
from src.services.chat_service import chat_service

router = APIRouter(prefix="/v1/chat", tags=["Conversational AI"])


@router.post("/query", response_model=ChatQueryResponse)
async def query_assistant(req: ChatQueryRequest) -> ChatQueryResponse:
    """Answers queries regarding corridor disruption risk, ST-GNN interpretations, and travel planning."""
    return await chat_service.answer_query(req)
