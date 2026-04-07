# app/repositories/ai_service_repository.py
"""SQLAlchemy queries for AI service definitions."""

from __future__ import annotations

import logging
from typing import List, Optional

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AIService

logger = logging.getLogger(__name__)


async def get_ai_service_by_id(session: AsyncSession, service_id: str) -> Optional[AIService]:
    """Fetch an AI service record by its service_id."""
    result = await session.execute(select(AIService).where(AIService.service_id == service_id))
    return result.scalars().first()


async def list_ai_services(session: AsyncSession) -> List[AIService]:
    """Fetch all AI services."""
    result = await session.execute(select(AIService).order_by(AIService.service_id))
    return list(result.scalars().all())


async def update_ai_service_type(
    session: AsyncSession, *, service_id: str, service_type: str
) -> Optional[AIService]:
    """Update the service_type for a specific AI service."""
    stmt = (
        update(AIService)
        .where(AIService.service_id == service_id)
        .values(service_type=service_type)
        .returning(AIService)
    )
    result = await session.execute(stmt)
    await session.commit()
    return result.scalars().first()

