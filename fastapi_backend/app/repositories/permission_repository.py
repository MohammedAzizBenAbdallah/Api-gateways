# app/repositories/permission_repository.py
"""Permission checks and permission audit log writes."""

from __future__ import annotations

from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import PermissionAuditLog, TenantServicePermission

import logging

logger = logging.getLogger(__name__)


async def check_tenant_service_permission_and_audit(
    session: AsyncSession,
    *,
    tenant_id: str,
    service_id: str,
    intent: Optional[str] = None,
    performed_by: str = "system",
) -> bool:
    """Return whether tenant is allowed and persist an audit log entry."""

    query = select(TenantServicePermission).where(
        TenantServicePermission.tenant_id == tenant_id,
        TenantServicePermission.service_id == service_id,
    )
    result = await session.execute(query)
    permission = result.scalars().first()
    is_allowed = permission is not None and bool(permission.allowed)

    audit_log = PermissionAuditLog(
        tenant_id=tenant_id,
        service_id=service_id,
        action="ALLOW" if is_allowed else "DENY",
        performed_by=performed_by,
        reason="Policy check passed" if is_allowed else "Policy check failed",
        intent=intent,
    )
    session.add(audit_log)
    await session.commit()
    return is_allowed

