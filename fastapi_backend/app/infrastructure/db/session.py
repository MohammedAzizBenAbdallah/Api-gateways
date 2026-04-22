# app/infrastructure/db/session.py
"""Async SQLAlchemy engine and session dependency."""

from __future__ import annotations

import logging
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy import text
from fastapi import Depends

from app.core.config import settings

logger = logging.getLogger(__name__)

# Convert postgresql:// to postgresql+asyncpg:// if needed
if settings.database_url.startswith("postgresql://"):
    ASYNC_DATABASE_URL = settings.database_url.replace("postgresql://", "postgresql+asyncpg://", 1)
else:
    ASYNC_DATABASE_URL = settings.database_url

engine = create_async_engine(ASYNC_DATABASE_URL, echo=False)
AsyncSessionLocal = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

async def get_db() -> AsyncSession:
    """FastAPI dependency that yields an AsyncSession."""
    async with AsyncSessionLocal() as session:
        yield session


from app.core.security import get_current_user

async def get_db_with_user(
    current_user: dict = Depends(get_current_user),
) -> AsyncSession:
    """FastAPI dependency that yields an AsyncSession with RLS variables set."""
    async with AsyncSessionLocal() as session:
        if current_user:
            tenant_id = current_user.get("tenant_id", "unknown")
            is_admin = "admin" in current_user.get("realm_access", {}).get("roles", [])
            
            # Set RLS session variables
            await session.execute(text("SELECT set_config('app.current_tenant', :t, true)"), {"t": str(tenant_id)})
            await session.execute(text("SELECT set_config('app.is_admin', :a, true)"), {"a": "true" if is_admin else "false"})
        
        yield session

