"""Append-only request lifecycle audit trail (ORK-024)."""

from __future__ import annotations

from sqlalchemy import Column, DateTime, Integer, String, Text, func

from app.models.base import Base


class RequestLifecycleEvent(Base):
    __tablename__ = "request_lifecycle_events"

    id = Column(Integer, primary_key=True, autoincrement=True)
    request_id = Column(String(255), nullable=False, index=True)
    tenant_id = Column(String(255), nullable=False, index=True)
    stage = Column(String(64), nullable=False)
    detail = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
