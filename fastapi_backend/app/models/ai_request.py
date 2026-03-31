# app/models/ai_request.py
"""ORM model for tracking AI request lifecycle."""

from __future__ import annotations

import logging

from sqlalchemy import Column, DateTime, ForeignKey, String

from app.models.base import Base

logger = logging.getLogger(__name__)


class AIRequestRecord(Base):
    __tablename__ = "ai_requests"

    request_id = Column(String, primary_key=True)
    tenant_id = Column(String, nullable=False)
    intent = Column(String, nullable=False)
    resolved_service_id = Column(String, ForeignKey("ai_services.service_id"), nullable=True)
    sensitivity = Column(String, nullable=False, default="LOW")
    resolved_sensitivity = Column(String, nullable=True)
    environment = Column(String, nullable=False, default="dev")
    status = Column(String, nullable=False, default="received")
    started_at = Column(DateTime, nullable=False)
    completed_at = Column(DateTime, nullable=True)
    error_detail = Column(String, nullable=True)

