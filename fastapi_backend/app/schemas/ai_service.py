# app/schemas/ai_service.py
"""Schemas for AI service administrative operations."""

from __future__ import annotations

from typing import Optional
from pydantic import BaseModel, ConfigDict


class AIServiceBaseSchema(BaseModel):
    service_id: str
    model_name: str
    provider_url: str
    provider_type: str = "ollama"
    description: Optional[str] = None
    service_type: str = "on-prem"


class AIServiceResponseSchema(AIServiceBaseSchema):
    model_config = ConfigDict(from_attributes=True)


class AIServiceUpdateSchema(BaseModel):
    service_type: str
