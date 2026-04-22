# app/api/admin/services.py
"""Admin endpoints for managing AI services."""

from __future__ import annotations

import logging
from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.middleware import verify_kong_header
from app.core.security import require_admin
from app.infrastructure.db.session import get_db, get_db_with_user
from app.repositories.ai_service_repository import list_ai_services, update_ai_service_type
from app.schemas.ai_service import AIServiceResponseSchema, AIServiceUpdateSchema

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/service-governance", tags=["Admin - Services"])


@router.get(
    "",
    response_model=List[AIServiceResponseSchema],
    dependencies=[Depends(verify_kong_header)],
)
async def get_services(
    db: AsyncSession = Depends(get_db_with_user),
    admin_user: Dict[str, Any] = Depends(require_admin),
) -> List[AIServiceResponseSchema]:
    _ = admin_user
    return await list_ai_services(db)


@router.patch(
    "/{service_id}",
    response_model=AIServiceResponseSchema,
    dependencies=[Depends(verify_kong_header)],
)
async def update_service(
    service_id: str,
    payload: AIServiceUpdateSchema,
    db: AsyncSession = Depends(get_db_with_user),
    admin_user: Dict[str, Any] = Depends(require_admin),
) -> AIServiceResponseSchema:
    _ = admin_user
    service = await update_ai_service_type(
        db, service_id=service_id, service_type=payload.service_type
    )
    if not service:
        raise HTTPException(status_code=404, detail="Service not found")
    return service
