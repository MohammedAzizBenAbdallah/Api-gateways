# app/models/governance_policy.py
"""SQLAlchemy model for governance policies."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from sqlalchemy import JSON, Column, DateTime, String, Boolean
from app.models.base import Base


class GovernancePolicy(Base):
    __tablename__ = "governance_policies"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    description = Column(String, nullable=True)
    # condition stores JSON like {"sensitivity": "HIGH", "tenant": "finance"}
    condition = Column(JSON, nullable=False, default={})
    # effect stores values like "deny_cloud", "allow_onprem_only", etc.
    effect = Column(String, nullable=False)
    is_active = Column(Boolean, nullable=False, default=True)
    
    version = Column(String, nullable=False, default="1.0.0")
    
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at = Column(
        DateTime(timezone=True), 
        default=lambda: datetime.now(timezone.utc), 
        onupdate=lambda: datetime.now(timezone.utc)
    )

    def __repr__(self) -> str:
        return f"<GovernancePolicy(id={self.id}, effect={self.effect})>"
