# app/api/admin/intent_mappings.py
"""Admin endpoints for intent mappings (CRUD and cache reload)."""

from __future__ import annotations

import logging
from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import IntentMappingAlreadyExistsError, IntentMappingNotFoundError
from app.core.middleware import verify_kong_header
from app.core.security import require_admin
from app.infrastructure.db.session import get_db, get_db_with_user
from app.schemas.intent_mapping import (
    IntentMappingCreateSchema,
    IntentMappingResponseSchema,
    IntentMappingUpdateSchema,
)
from app.services.intent_mappings_service import IntentMappingsService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin/intent-mappings", tags=["Admin - Intent Mappings"])


def get_intent_mappings_service(request: Request) -> IntentMappingsService:
    return request.app.state.intent_mappings_service


@router.get(
    "",
    response_model=List[IntentMappingResponseSchema],
    dependencies=[Depends(verify_kong_header)],
)
async def list_mappings(
    db: AsyncSession = Depends(get_db_with_user),
    admin_user: Dict[str, Any] = Depends(require_admin),
    intent_mappings_service: IntentMappingsService = Depends(get_intent_mappings_service),
) -> List[IntentMappingResponseSchema]:
    _ = admin_user  # role enforced by require_admin
    return await intent_mappings_service.list_mappings(db)


@router.get(
    "/{mapping_id}",
    response_model=IntentMappingResponseSchema,
    dependencies=[Depends(verify_kong_header)],
)
async def get_mapping(
    mapping_id: str,
    db: AsyncSession = Depends(get_db_with_user),
    admin_user: Dict[str, Any] = Depends(require_admin),
    intent_mappings_service: IntentMappingsService = Depends(get_intent_mappings_service),
) -> IntentMappingResponseSchema:
    _ = admin_user
    try:
        return await intent_mappings_service.get_mapping(db, mapping_id)
    except IntentMappingNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post(
    "",
    response_model=IntentMappingResponseSchema,
    dependencies=[Depends(verify_kong_header)],
)
async def create_mapping(
    payload: IntentMappingCreateSchema,
    db: AsyncSession = Depends(get_db_with_user),
    admin_user: Dict[str, Any] = Depends(require_admin),
    intent_mappings_service: IntentMappingsService = Depends(get_intent_mappings_service),
) -> IntentMappingResponseSchema:
    try:
        created_by = admin_user.get("email", "unknown")
        return await intent_mappings_service.create_mapping(
            db,
            payload=payload,
            created_by=created_by,
        )
    except IntentMappingAlreadyExistsError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.put(
    "/{mapping_id}",
    response_model=IntentMappingResponseSchema,
    dependencies=[Depends(verify_kong_header)],
)
async def update_mapping(
    mapping_id: str,
    payload: IntentMappingUpdateSchema,
    db: AsyncSession = Depends(get_db_with_user),
    admin_user: Dict[str, Any] = Depends(require_admin),
    intent_mappings_service: IntentMappingsService = Depends(get_intent_mappings_service),
) -> IntentMappingResponseSchema:
    try:
        performed_by = admin_user.get("email", "unknown")
        return await intent_mappings_service.update_mapping(
            db,
            mapping_id=mapping_id,
            payload=payload,
            performed_by=performed_by,
        )
    except IntentMappingNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.delete(
    "/{mapping_id}",
    response_model=IntentMappingResponseSchema,
    dependencies=[Depends(verify_kong_header)],
)
async def delete_mapping(
    mapping_id: str,
    db: AsyncSession = Depends(get_db_with_user),
    admin_user: Dict[str, Any] = Depends(require_admin),
    intent_mappings_service: IntentMappingsService = Depends(get_intent_mappings_service),
) -> IntentMappingResponseSchema:
    try:
        performed_by = admin_user.get("email", "unknown")
        return await intent_mappings_service.delete_mapping(
            db,
            mapping_id=mapping_id,
            performed_by=performed_by,
        )
    except IntentMappingNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/reload", dependencies=[Depends(verify_kong_header)])
async def reload_cache(
    admin_user: Dict[str, Any] = Depends(require_admin),
    db: AsyncSession = Depends(get_db_with_user),
    intent_mappings_service: IntentMappingsService = Depends(get_intent_mappings_service),
) -> Dict[str, Any]:
    _ = admin_user
    result = await intent_mappings_service.reload_cache(db)
    return {"message": "Cache reload triggered", "version": result["version"]}

