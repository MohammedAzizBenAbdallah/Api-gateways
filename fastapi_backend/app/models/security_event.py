# app/models/security_event.py
"""SQLAlchemy model for security events (prompt injection blocks, PII redactions)."""

from __future__ import annotations

from sqlalchemy import Column, DateTime, Float, Integer, String, Text, func
from app.models.base import Base


class SecurityEvent(Base):
    __tablename__ = "security_events"

    id = Column(Integer, primary_key=True, autoincrement=True)
    event_type = Column(String(50), nullable=False)       # "prompt_injection", "pii_redaction"
    tenant_id = Column(String(255), nullable=False)
    request_id = Column(String(255), nullable=True)
    prompt_hash = Column(String(64), nullable=True)        # SHA-256 hash (never plaintext)
    matched_patterns = Column(Text, nullable=True)          # JSON list of matched pattern names
    score = Column(Float, nullable=True)
    decision = Column(String(20), nullable=False)           # "blocked", "allowed", "redacted"
    redacted_types = Column(Text, nullable=True)            # JSON list of PII types found
    redaction_count = Column(Integer, default=0)
    metadata_extra = Column(Text, nullable=True)            # Any additional JSON context
    created_at = Column(DateTime(timezone=True), server_default=func.now())
