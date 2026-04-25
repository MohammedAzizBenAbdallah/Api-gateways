# app/api/admin/policies.py
"""Admin endpoints for governance policies."""

from __future__ import annotations

import logging
from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import PolicySyncError
from app.core.middleware import verify_kong_header
from app.core.security import require_admin
from app.infrastructure.db.session import get_db, get_db_with_user
from app.repositories.policy_repository import (
    create_policy,
    delete_policy,
    get_policy,
    list_policies,
    update_policy,
)
from app.schemas.policy import (
    GovernancePolicyCreate,
    GovernancePolicyResponse,
    GovernancePolicyUpdate,
)
from app.services.policy_service import PolicyService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin/policies", tags=["Admin - Policies"])


def get_policy_service(request: Request) -> PolicyService:
    return request.app.state.policy_service


async def _safe_sync(policy_service: PolicyService, db: AsyncSession) -> Dict[str, Any]:
    """Wrap sync_from_db so OPA strict-sync failures surface as HTTP 502.

    A 502 is more accurate than a 500 here because the upstream dependency
    (OPA) is the failing component; callers (frontend / curl) can branch on it.
    """
    try:
        return await policy_service.sync_from_db(db)
    except PolicySyncError as exc:
        logger.error("Policy sync to OPA failed: %s", exc.detail)
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail={
                "error": "policy_sync_failed",
                "reason": exc.reason,
                "detail": exc.detail,
                "status": policy_service.get_status(),
            },
        ) from exc


@router.get(
    "",
    response_model=List[GovernancePolicyResponse],
    dependencies=[Depends(verify_kong_header)],
)
async def list_governance_policies(
    db: AsyncSession = Depends(get_db_with_user),
    admin_user: Dict[str, Any] = Depends(require_admin),
) -> List[GovernancePolicyResponse]:
    _ = admin_user
    return await list_policies(db)


@router.get(
    "/status",
    dependencies=[Depends(verify_kong_header)],
)
async def policy_sync_status(
    admin_user: Dict[str, Any] = Depends(require_admin),
    policy_service: PolicyService = Depends(get_policy_service),
) -> Dict[str, Any]:
    """Expose OPA sync state (hash, version, last_sync_ok, last_error).

    Consumed by the admin governance UI to show whether the local policy
    cache and OPA are currently in sync.
    """
    _ = admin_user
    return policy_service.get_status()


@router.get(
    "/{policy_id}",
    response_model=GovernancePolicyResponse,
    dependencies=[Depends(verify_kong_header)],
)
async def get_governance_policy(
    policy_id: str,
    db: AsyncSession = Depends(get_db_with_user),
    admin_user: Dict[str, Any] = Depends(require_admin),
) -> GovernancePolicyResponse:
    _ = admin_user
    policy = await get_policy(db, policy_id)
    if not policy:
        raise HTTPException(status_code=404, detail="Policy not found")
    return policy


@router.post(
    "",
    response_model=GovernancePolicyResponse,
    dependencies=[Depends(verify_kong_header)],
)
async def create_governance_policy(
    payload: GovernancePolicyCreate,
    db: AsyncSession = Depends(get_db_with_user),
    admin_user: Dict[str, Any] = Depends(require_admin),
    policy_service: PolicyService = Depends(get_policy_service),
) -> GovernancePolicyResponse:
    _ = admin_user
    policy = await create_policy(db, payload)
    await _safe_sync(policy_service, db)
    return policy


@router.put(
    "/{policy_id}",
    response_model=GovernancePolicyResponse,
    dependencies=[Depends(verify_kong_header)],
)
async def update_governance_policy(
    policy_id: str,
    payload: GovernancePolicyUpdate,
    db: AsyncSession = Depends(get_db_with_user),
    admin_user: Dict[str, Any] = Depends(require_admin),
    policy_service: PolicyService = Depends(get_policy_service),
) -> GovernancePolicyResponse:
    _ = admin_user
    policy = await update_policy(db, policy_id, payload)
    if not policy:
        raise HTTPException(status_code=404, detail="Policy not found")

    await _safe_sync(policy_service, db)
    return policy


@router.delete(
    "/{policy_id}",
    dependencies=[Depends(verify_kong_header)],
)
async def delete_governance_policy(
    policy_id: str,
    db: AsyncSession = Depends(get_db_with_user),
    admin_user: Dict[str, Any] = Depends(require_admin),
    policy_service: PolicyService = Depends(get_policy_service),
) -> Dict[str, Any]:
    _ = admin_user
    success = await delete_policy(db, policy_id)
    if not success:
        raise HTTPException(status_code=404, detail="Policy not found")

    await _safe_sync(policy_service, db)
    return {"message": "Policy deleted successfully"}


@router.post("/reload", dependencies=[Depends(verify_kong_header)])
async def reload_policies(
    db: AsyncSession = Depends(get_db),
    admin_user: Dict[str, Any] = Depends(require_admin),
    policy_service: PolicyService = Depends(get_policy_service),
) -> Dict[str, Any]:
    _ = admin_user
    stats = await _safe_sync(policy_service, db)
    return {"message": "Policies reloaded from database", "stats": stats}
