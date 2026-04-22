# app/infrastructure/db/session.py
"""Async SQLAlchemy engine and session dependency."""

from __future__ import annotations

import logging
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy import text
from fastapi import Depends

from app.core.config import settings
from app.infrastructure.tenant_context import current_is_admin, current_tenant_id

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
    """Yield an AsyncSession scoped to the current user.

    Responsibilities:
      - Set PostgreSQL RLS session variables so row-level policies see the
        correct tenant / role.
      - Populate the `current_tenant_id` / `current_is_admin` ContextVars so
        the ORM-level tenant filter in ``tenant_filters`` can inject a
        `WHERE tenant_id = :current_tenant` predicate.
      - Reset both ContextVars in a ``finally`` block so a pooled worker
        cannot leak one request's tenant scope into the next request.
    """
    tenant_token = None
    admin_token = None
    async with AsyncSessionLocal() as session:
        if current_user:
            tenant_id = current_user.get("tenant_id", "unknown")
            is_admin = "admin" in current_user.get("realm_access", {}).get("roles", [])

            await session.execute(
                text("SELECT set_config('app.current_tenant', :t, true)"),
                {"t": str(tenant_id)},
            )
            await session.execute(
                text("SELECT set_config('app.is_admin', :a, true)"),
                {"a": "true" if is_admin else "false"},
            )

            tenant_token = current_tenant_id.set(str(tenant_id))
            admin_token = current_is_admin.set(bool(is_admin))

        try:
            yield session
        finally:
            if admin_token is not None:
                current_is_admin.reset(admin_token)
            if tenant_token is not None:
                current_tenant_id.reset(tenant_token)

