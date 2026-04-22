# app/api/governance.py
from __future__ import annotations
import logging
from typing import Any, Dict
from fastapi import APIRouter, Depends, Request
from app.core.middleware import verify_kong_header
from app.core.security import get_current_user
from app.services.quota_service import QuotaService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/governance", tags=["Governance"])


def get_quota_service(request: Request) -> QuotaService:
    """Fetch the QuotaService instance from app state."""
    return request.app.state.quota_service


@router.get("/quota-status", dependencies=[Depends(verify_kong_header)])
async def get_quota_status(
    current_user: Dict[str, Any] = Depends(get_current_user),
    quota_service: QuotaService = Depends(get_quota_service),
) -> Dict[str, Any]:
    """Retrieve live token usage and quota for the current tenant."""
    tenant_id = current_user.get("tenant_id")
    if not tenant_id:
        return {"error": "Tenant context missing"}
    
    status = await quota_service.get_quota_status(tenant_id)
    return status

