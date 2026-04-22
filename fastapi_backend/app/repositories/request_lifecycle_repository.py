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
    event = RequestLifecycleEvent(
        request_id=request_id,
        tenant_id=tenant_id,
        stage=stage,
        detail=json.dumps(detail) if detail else None,
    )
    session.add(event)
    await session.commit()
