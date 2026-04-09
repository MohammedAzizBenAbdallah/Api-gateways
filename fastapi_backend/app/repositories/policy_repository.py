# app/repositories/policy_repository.py
"""Repository for database operations on governance policies."""

from __future__ import annotations

import logging
from typing import List, Optional
from sqlalchemy import select, update, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.governance_policy import GovernancePolicy
from app.schemas.policy import GovernancePolicyCreate, GovernancePolicyUpdate

logger = logging.getLogger(__name__)


async def list_policies(db: AsyncSession) -> List[GovernancePolicy]:
    """Fetch all governance policies, ordered by creation date."""
    result = await db.execute(
        select(GovernancePolicy).order_by(GovernancePolicy.created_at.desc())
    )
    return list(result.scalars().all())


async def get_policy(db: AsyncSession, policy_id: str) -> Optional[GovernancePolicy]:
    """Fetch a single policy by ID."""
    result = await db.execute(
        select(GovernancePolicy).where(GovernancePolicy.id == policy_id)
    )
    return result.scalar_one_or_none()


async def create_policy(
    db: AsyncSession, payload: GovernancePolicyCreate
) -> GovernancePolicy:
    """Create a new governance policy."""
    db_policy = GovernancePolicy(
        description=payload.description,
        condition=payload.condition.model_dump(),
        effect=payload.effect,
        is_active=payload.is_active,
        version=payload.version,
    )
    db.add(db_policy)
    await db.commit()
    await db.refresh(db_policy)
    return db_policy


async def update_policy(
    db: AsyncSession, policy_id: str, payload: GovernancePolicyUpdate
) -> Optional[GovernancePolicy]:
    """Update an existing governance policy."""
    update_data = payload.model_dump(exclude_unset=True)

    if not update_data:
        return await get_policy(db, policy_id)

    await db.execute(
        update(GovernancePolicy)
        .where(GovernancePolicy.id == policy_id)
        .values(**update_data)
    )
    await db.commit()
    return await get_policy(db, policy_id)


async def delete_policy(db: AsyncSession, policy_id: str) -> bool:
    """Delete a governance policy."""
    result = await db.execute(
        delete(GovernancePolicy).where(GovernancePolicy.id == policy_id)
    )
    await db.commit()
    return result.rowcount > 0
