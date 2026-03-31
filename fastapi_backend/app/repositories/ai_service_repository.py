# app/repositories/ai_service_repository.py
"""SQLAlchemy queries for AI service definitions."""

from __future__ import annotations

import logging
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AIService

logger = logging.getLogger(__name__)


async def get_ai_service_by_id(session: AsyncSession, service_id: str) -> Optional[AIService]:
    """Fetch an AI service record by its service_id."""
    result = await session.execute(select(AIService).where(AIService.service_id == service_id))
    return result.scalars().first()

