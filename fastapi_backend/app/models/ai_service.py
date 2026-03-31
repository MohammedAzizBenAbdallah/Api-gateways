# app/models/ai_service.py
"""ORM model for AI service definitions."""

from __future__ import annotations

import logging

from sqlalchemy import Column, String, Text

from app.models.base import Base

logger = logging.getLogger(__name__)


class AIService(Base):
    __tablename__ = "ai_services"

    service_id = Column(String, primary_key=True, index=True)
    model_name = Column(String, nullable=False)
    provider_url = Column(String, nullable=False)
    provider_type = Column(String, default="ollama")
    description = Column(Text, nullable=True)

