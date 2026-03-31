# app/repositories/intent_routing_repository.py
"""SQLAlchemy repository for intent routing and related audit logs."""

from __future__ import annotations

import logging
import json
from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import update as sqlalchemy_update

from app.models import IntentMappingAuditLog, IntentRouting

logger = logging.getLogger(__name__)


async def list_active_intent_mappings(session: AsyncSession) -> List[IntentRouting]:
    """List all active mappings."""
    result = await session.execute(select(IntentRouting).where(IntentRouting.is_active == True))
    return list(result.scalars().all())


async def get_intent_mapping_by_intent_name(
    session: AsyncSession,
    *,
    intent_name: str,
) -> Optional[IntentRouting]:
    result = await session.execute(select(IntentRouting).where(IntentRouting.intent_name == intent_name))
    return result.scalars().first()


async def get_intent_mapping_by_id(session: AsyncSession, mapping_id: str) -> Optional[IntentRouting]:
    # mapping_id is stored as UUID, but the admin API provides it as a string.
    result = await session.execute(select(IntentRouting).where(IntentRouting.id == mapping_id))
    return result.scalars().first()


async def create_intent_mapping(
    session: AsyncSession,
    *,
    intent_name: str,
    service_id: str,
    taxonomy_version: str,
    created_by: str,
) -> IntentRouting:
    mapping = IntentRouting(
        intent_name=intent_name,
        service_id=service_id,
        taxonomy_version=taxonomy_version,
        is_active=True,
        created_by=created_by,
    )
    session.add(mapping)
    await session.flush()

    audit = IntentMappingAuditLog(
        action="MAPPING_CREATED",
        performed_by=created_by,
        entity_id=str(mapping.id),
        new_value=json.loads(json.dumps({  # ensure JSON-serializable structure
            "intent_name": intent_name,
            "service_id": service_id,
            "taxonomy_version": taxonomy_version,
            "is_active": True,
        })),
        old_value=None,
    )
    session.add(audit)
    await session.commit()
    await session.refresh(mapping)
    return mapping


async def update_intent_mapping(
    session: AsyncSession,
    *,
    mapping: IntentRouting,
    update_data: dict,
    performed_by: str,
) -> IntentRouting:
    old_value = {
        "service_id": mapping.service_id,
        "is_active": mapping.is_active,
        "taxonomy_version": mapping.taxonomy_version,
    }

    for key, value in update_data.items():
        setattr(mapping, key, value)

    audit = IntentMappingAuditLog(
        action="MAPPING_UPDATED",
        performed_by=performed_by,
        entity_id=str(mapping.id),
        old_value=old_value,
        new_value=update_data,
    )
    session.add(audit)
    await session.commit()
    await session.refresh(mapping)
    return mapping


async def soft_delete_intent_mapping(
    session: AsyncSession,
    *,
    mapping: IntentRouting,
    performed_by: str,
) -> IntentRouting:
    old_value = {"is_active": mapping.is_active}
    mapping.is_active = False

    audit = IntentMappingAuditLog(
        action="MAPPING_DEACTIVATED",
        performed_by=performed_by,
        entity_id=str(mapping.id),
        old_value=old_value,
        new_value={"is_active": False},
    )
    session.add(audit)
    await session.commit()
    await session.refresh(mapping)
    return mapping

