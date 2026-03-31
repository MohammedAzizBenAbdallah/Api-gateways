# app/repositories/ai_request_repository.py
"""SQLAlchemy repository for ai_requests lifecycle persistence."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AIRequestRecord

logger = logging.getLogger(__name__)


async def create_ai_request(
    session: AsyncSession,
    *,
    request_id: str,
    tenant_id: str,
    intent: str,
    resolved_service_id: str,
    sensitivity: str,
    environment: str,
    status: str,
    started_at: datetime,
) -> AIRequestRecord:
    """Insert a new ai_requests record."""
    record = AIRequestRecord(
        request_id=request_id,
        tenant_id=tenant_id,
        intent=intent,
        resolved_service_id=resolved_service_id,
        sensitivity=sensitivity,
        environment=environment,
        status=status,
        started_at=started_at,
    )
    session.add(record)
    await session.commit()
    await session.refresh(record)
    return record


async def update_ai_request_status(
    session: AsyncSession,
    *,
    request_id: str,
    status: str,
    completed_at: Optional[datetime] = None,
    error_detail: Optional[str] = None,
) -> None:
    """Update ai_requests status and optional completion fields."""
    values: dict = {"status": status}
    if completed_at is not None:
        values["completed_at"] = completed_at
    if error_detail is not None:
        values["error_detail"] = error_detail

    await session.execute(
        update(AIRequestRecord).where(AIRequestRecord.request_id == request_id).values(**values)
    )
    await session.commit()


async def update_resolved_sensitivity(
    session: AsyncSession,
    *,
    request_id: str,
    resolved_sensitivity: str,
) -> None:
    """Persist the resolved sensitivity classification."""
    await session.execute(
        update(AIRequestRecord)
        .where(AIRequestRecord.request_id == request_id)
        .values(resolved_sensitivity=resolved_sensitivity)
    )
    await session.commit()

