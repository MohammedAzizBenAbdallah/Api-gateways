# app/models/security_pattern.py
"""SQLAlchemy model for Security Patterns."""

from __future__ import annotations

from sqlalchemy import Column, Integer, String, Text, DECIMAL, Boolean, DateTime
from sqlalchemy.sql import func

from app.models.base import Base

class SecurityPattern(Base):
    __tablename__ = "security_patterns"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(255), unique=True, nullable=False)
    pattern = Column(Text, nullable=False)
    weight = Column(DECIMAL(5, 2), default=1.0)
    description = Column(Text, nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    created_by = Column(String(255), default='admin')
