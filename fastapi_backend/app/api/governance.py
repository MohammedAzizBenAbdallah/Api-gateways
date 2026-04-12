# app/api/governance.py
from __future__ import annotations
import logging
from typing import Any, Dict
from fastapi import APIRouter, Depends
from app.api.dependencies import get_ai_request_service
from app.core.middleware import verify_kong_header
from app.core.security import get_current_user
from app.services.ai_request_service import AIRequestService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/governance", tags=["Governance"])

@router.get("/quota-status", dependencies=[Depends(verify_kong_header)])
async def get_quota_status(
    current_user: Dict[str, Any] = Depends(get_current_user),
    ai_request_service: AIRequestService = Depends(get_ai_request_service),
) -> Dict[str, Any]:
    """Retrieve live token usage and quota for the current tenant."""
    tenant_id = current_user.get("tenant_id")
    if not tenant_id:
        return {"error": "Tenant context missing"}
    
    # We use the quota_service integrated into ai_request_service
    status = await ai_request_service._quota_service.get_quota_status(tenant_id)
    return status
