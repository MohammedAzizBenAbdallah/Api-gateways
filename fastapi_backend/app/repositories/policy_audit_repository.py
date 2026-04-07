# app/repositories/policy_audit_repository.py
"""SQLAlchemy operations for policy evaluation audit logging."""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import PolicyEvaluationAuditLog

logger = logging.getLogger(__name__)


async def create_policy_audit_log(
    session: AsyncSession,
    *,
    request_id: str,
    policy_id: str,
    effect: str,
    decision: str,
    context: Optional[Dict[str, Any]] = None,
) -> PolicyEvaluationAuditLog:
    """Create a new policy evaluation audit log entry."""
    log_entry = PolicyEvaluationAuditLog(
        request_id=request_id,
        policy_id=policy_id,
        effect=effect,
        decision=decision,
        context=context,
    )
    session.add(log_entry)
    await session.commit()
    await session.refresh(log_entry)
    return log_entry
