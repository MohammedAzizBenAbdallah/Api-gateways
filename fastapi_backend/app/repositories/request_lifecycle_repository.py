"""Append-only lifecycle events for AI requests (ORK-024)."""

from __future__ import annotations

import json
import logging
from typing import Any, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.request_lifecycle import RequestLifecycleEvent

logger = logging.getLogger(__name__)


async def append_lifecycle_event(
    session: AsyncSession,
    *,
    request_id: str,
    tenant_id: str,
    stage: str,
    detail: Optional[dict[str, Any]] = None,
) -> None:
    """Stage a lifecycle event row and flush it to the DB.

    The caller owns the transaction: this helper never commits. Flushing
    (rather than committing) ensures the row participates in the surrounding
    unit of work and gets a PK, while letting the service layer / request
    middleware decide when to commit or roll back.
    """
    event = RequestLifecycleEvent(
        request_id=request_id,
        tenant_id=tenant_id,
        stage=stage,
        detail=json.dumps(detail) if detail else None,
    )
    session.add(event)
    await session.flush()
