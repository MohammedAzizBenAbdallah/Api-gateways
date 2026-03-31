# app/models/intent_routing.py
"""ORM model for mapping intent names to AI services."""

from __future__ import annotations

import logging

from sqlalchemy import Column, String, Boolean, DateTime, ForeignKey
from sqlalchemy.sql import func
from sqlalchemy.dialects.postgresql import UUID

from app.models.base import Base

logger = logging.getLogger(__name__)


class IntentRouting(Base):
    __tablename__ = "intent_routing"

    id = Column(
        UUID(as_uuid=True),
        primary_key=True,
        index=True,
        server_default=func.gen_random_uuid(),
    )
    intent_name = Column(String, unique=True, nullable=False, index=True)
    service_id = Column(String, ForeignKey("ai_services.service_id"), nullable=False)
    is_active = Column(Boolean, default=True)
    taxonomy_version = Column(String, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    created_by = Column(String, nullable=False)

