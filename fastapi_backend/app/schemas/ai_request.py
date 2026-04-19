# app/schemas/ai_request.py
"""AI request/response schemas including SensitivityLevel."""

from __future__ import annotations

from enum import Enum
import logging
from typing import Any, Dict, List, Literal

from pydantic import BaseModel, ConfigDict

logger = logging.getLogger(__name__)


class SensitivityLevel(str, Enum):
    """Sensitivity classification for request content."""

    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class MessageSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: str
    content: str


class AIRequestPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    messages: List[MessageSchema]


class AIRequestMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sensitivity: SensitivityLevel = SensitivityLevel.LOW
    environment: Literal["dev", "prod"] = "dev"


class AIRequestSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")

    intent: str = "general_chat"
    payload: AIRequestPayload
    metadata: AIRequestMetadata


class AIRequestResponseSchema(BaseModel):
    """Response schema for JSON fallback path."""

    request_id: str
    intent: str
    resolved_service: str
    response: Dict[str, Any]

