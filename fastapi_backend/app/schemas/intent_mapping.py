# app/schemas/intent_mapping.py
"""Schemas for admin intent mapping CRUD."""

from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import UUID

import logging
from pydantic import BaseModel, ConfigDict

logger = logging.getLogger(__name__)


class IntentMappingBaseSchema(BaseModel):
    intent_name: str
    service_id: str
    taxonomy_version: str = "1.0.0"
    is_active: bool = True


class IntentMappingCreateSchema(IntentMappingBaseSchema):
    """Create schema for intent mapping."""


class IntentMappingUpdateSchema(BaseModel):
    service_id: Optional[str] = None
    is_active: Optional[bool] = None
    taxonomy_version: Optional[str] = None


class IntentMappingResponseSchema(IntentMappingBaseSchema):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    created_at: datetime
    updated_at: datetime
    created_by: str

