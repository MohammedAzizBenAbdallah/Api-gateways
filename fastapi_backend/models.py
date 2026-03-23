from sqlalchemy import Column, Integer, String, Boolean, JSON, DateTime, ForeignKey
from sqlalchemy.sql import func
from database import Base

class AIService(Base):
    __tablename__ = "ai_services"

    service_id = Column(String, primary_key=True, index=True)
    model_name = Column(String, nullable=False)
    provider_url = Column(String, nullable=False)
    provider_type = Column(String, default="ollama")
    description = Column(String)

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
    intent = Column(String, nullable=True)  # populated by /ai/request endpoint


class IntentRouting(Base):
    __tablename__ = "intent_routing"

    intent = Column(String, primary_key=True, index=True)
    service_id = Column(String, ForeignKey("ai_services.service_id"), nullable=False)
    description = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class AIRequestRecord(Base):
    __tablename__ = "ai_requests"

    request_id          = Column(String, primary_key=True)
    tenant_id           = Column(String, nullable=False)
    intent              = Column(String, nullable=False)
    resolved_service_id = Column(String, ForeignKey("ai_services.service_id"), nullable=True)
    sensitivity         = Column(String, nullable=False, default="LOW")
    environment         = Column(String, nullable=False, default="dev")
    status              = Column(String, nullable=False, default="received")
    started_at          = Column(DateTime, nullable=False)
    completed_at        = Column(DateTime, nullable=True)
    error_detail        = Column(String, nullable=True)

