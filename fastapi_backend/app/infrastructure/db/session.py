# app/infrastructure/db/session.py
"""Async SQLAlchemy engine and session dependency."""

from __future__ import annotations

import logging
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import settings

logger = logging.getLogger(__name__)

# Convert postgresql:// to postgresql+asyncpg:// if needed
if settings.database_url.startswith("postgresql://"):
    ASYNC_DATABASE_URL = settings.database_url.replace("postgresql://", "postgresql+asyncpg://", 1)
else:
    ASYNC_DATABASE_URL = settings.database_url

engine = create_async_engine(ASYNC_DATABASE_URL, echo=True)
AsyncSessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

async def get_db() -> AsyncSession:
    """FastAPI dependency that yields an AsyncSession."""
    async with AsyncSessionLocal() as session:
        yield session

