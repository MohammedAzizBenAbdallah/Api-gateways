# app/services/intent_mappings_service.py
"""Business logic for CRUD operations on intent mappings."""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional, TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover
    from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import (
    IntentMappingAlreadyExistsError,
    IntentMappingNotFoundError,
)
from app.repositories.intent_routing_repository import (
    create_intent_mapping,
    get_intent_mapping_by_id,
    get_intent_mapping_by_intent_name,
    list_active_intent_mappings,
    soft_delete_intent_mapping,
    update_intent_mapping,
)
from app.repositories.ai_service_repository import get_ai_service_by_id
from app.services.intent_cache_service import IntentCacheService

logger = logging.getLogger(__name__)


class IntentMappingsService:
    """Orchestrate intent mapping CRUD and cache reload."""

    def __init__(self, *, intent_cache_service: IntentCacheService) -> None:
        self._intent_cache_service = intent_cache_service

    async def list_mappings(self, db: "AsyncSession") -> list[Any]:
        return await list_active_intent_mappings(db)

    async def get_mapping(self, db: "AsyncSession", mapping_id: str) -> Any:
        mapping = await get_intent_mapping_by_id(db, mapping_id=mapping_id)
        if mapping is None:
            raise IntentMappingNotFoundError(mapping_id=mapping_id)
        return mapping

    async def create_mapping(
        self,
        db: "AsyncSession",
        *,
        payload: Any,
        created_by: str,
    ) -> Any:
        existing = await get_intent_mapping_by_intent_name(db, intent_name=payload.intent_name)
        if existing is not None:
            raise IntentMappingAlreadyExistsError(intent_name=payload.intent_name)

        return await create_intent_mapping(
            db,
            intent_name=payload.intent_name,
            service_id=payload.service_id,
            taxonomy_version=payload.taxonomy_version,
            created_by=created_by,
        )

    async def update_mapping(
        self,
        db: "AsyncSession",
        *,
        mapping_id: str,
        payload: Any,
        performed_by: str,
    ) -> Any:
        mapping = await get_intent_mapping_by_id(db, mapping_id=mapping_id)
        if mapping is None:
            raise IntentMappingNotFoundError(mapping_id=mapping_id)

        update_data: Dict[str, Any] = payload.model_dump(exclude_unset=True)
        return await update_intent_mapping(
            db,
            mapping=mapping,
            update_data=update_data,
            performed_by=performed_by,
        )

    async def delete_mapping(
        self,
        db: "AsyncSession",
        *,
        mapping_id: str,
        performed_by: str,
    ) -> Any:
        mapping = await get_intent_mapping_by_id(db, mapping_id=mapping_id)
        if mapping is None:
            raise IntentMappingNotFoundError(mapping_id=mapping_id)

        return await soft_delete_intent_mapping(
            db,
            mapping=mapping,
            performed_by=performed_by,
        )

    async def reload_cache(self, db: "AsyncSession") -> Dict[str, str]:
        await self._intent_cache_service.force_reload(session=db)
        return {"version": self._intent_cache_service.version}

