# app/models/usage.py
from __future__ import annotations
from datetime import datetime
from sqlalchemy import Column, Integer, String, DateTime, Numeric
from app.models.base import Base

class UsageTokenLog(Base):
    __tablename__ = "usage_token_logs"

    id = Column(Integer, primary_key=True, index=True)
    request_id = Column(String(255), nullable=False, index=True)
    tenant_id = Column(String(255), nullable=False, index=True)
    service_id = Column(String(255), nullable=False)
    model_name = Column(String(255))
    input_tokens = Column(Integer, default=0)
    output_tokens = Column(Integer, default=0)
    total_tokens = Column(Integer, default=0)
    cost_estimate = Column(Numeric(10, 5), default=0)
    created_at = Column(DateTime, default=datetime.utcnow)
