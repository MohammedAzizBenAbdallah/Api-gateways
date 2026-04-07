# app/models/permission.py
"""ORM models for tenant permissions and permission audit logs."""

from __future__ import annotations

import logging

from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Integer, JSON, String
from sqlalchemy.sql import func

from app.models.base import Base

logger = logging.getLogger(__name__)


class TenantServicePermission(Base):
    __tablename__ = "tenant_service_permissions"

    tenant_id = Column(String, primary_key=True)
    service_id = Column(String, primary_key=True)
    allowed = Column(Boolean, default=True)
    granted_by = Column(String)
    granted_at = Column(DateTime(timezone=True), server_default=func.now())


class PermissionAuditLog(Base):
    __tablename__ = "permission_audit_logs"

    id = Column(Integer, primary_key=True, index=True)
    tenant_id = Column(String)
    service_id = Column(String)
    action = Column(String)
    performed_by = Column(String)
    performed_at = Column(DateTime(timezone=True), server_default=func.now())
    reason = Column(String)
    intent = Column(String, nullable=True)


class IntentMappingAuditLog(Base):
    __tablename__ = "intent_mapping_audit_logs"

    id = Column(Integer, primary_key=True, index=True)
    action = Column(String, nullable=False)
    performed_by = Column(String, nullable=False)
    entity_id = Column(String, nullable=False)
    old_value = Column(JSON, nullable=True)
    new_value = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class PolicyEvaluationAuditLog(Base):
    __tablename__ = "policy_evaluation_audit_logs"

    id = Column(Integer, primary_key=True, index=True)
    request_id = Column(String, nullable=False)
    policy_id = Column(String, nullable=False)
    effect = Column(String, nullable=False)
    decision = Column(String, nullable=False)
    context = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

