# app/api/admin/quotas_admin.py
import logging
import yaml
from pathlib import Path
from typing import Dict, Any

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from app.core.middleware import verify_kong_header
from app.core.security import get_current_user

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/admin/quotas",
    tags=["Admin - Quota Management"],
    dependencies=[Depends(verify_kong_header), Depends(get_current_user)],
)

class QuotaUpdateRequest(BaseModel):
    max_tokens: int
    reset_period: str = "daily"
    is_active: bool = True

def _get_quotas_file(request: Request) -> Path:
    # Get the file path from the QuotaService instance
    quota_svc = request.app.state.quota_service
    return Path(quota_svc.quotas_file)

@router.get("")
async def get_all_quotas(request: Request) -> Dict[str, Any]:
    """Retrieve all tenant quotas directly from the configuration file."""
    quota_svc = request.app.state.quota_service
    quota_file = Path(quota_svc.quotas_file)
    
    if not quota_file.exists():
        return {"tenants": [], "defaults": {}}
        
    try:
        with open(quota_file, "r") as f:
            data = yaml.safe_load(f) or {}
            
        # Enrich the configuration with live usage data from Redis
        tenants = data.get("tenants", [])
        enriched_tenants = []
        for t in tenants:
            tenant_id = t["id"]
            # Fetch live usage
            status = await quota_svc.get_quota_status(tenant_id)
            enriched_tenants.append({
                "id": tenant_id,
                "max_tokens": t.get("max_tokens", 0),
                "reset_period": t.get("reset_period", "daily"),
                "is_active": t.get("is_active", True),
                "used_tokens": status.get("used_tokens", 0),
                "percent_used": status.get("percent_used", 0)
            })
            
        return {
            "tenants": enriched_tenants,
            "defaults": data.get("defaults", {})
        }
    except Exception as e:
        logger.error(f"Failed to read quotas file: {e}")
        raise HTTPException(status_code=500, detail="Failed to read quotas configuration")

@router.put("/{tenant_id}")
async def update_tenant_quota(
    tenant_id: str,
    update: QuotaUpdateRequest,
    request: Request
):
    """Update a tenant's token quota and reload the service."""
    quota_svc = request.app.state.quota_service
    quota_file = Path(quota_svc.quotas_file)
    
    try:
        data = {}
        if quota_file.exists():
            with open(quota_file, "r") as f:
                data = yaml.safe_load(f) or {}
                
        if "tenants" not in data:
            data["tenants"] = []
            
        # Find and update or append
        found = False
        for t in data["tenants"]:
            if t.get("id") == tenant_id:
                t["max_tokens"] = update.max_tokens
                t["reset_period"] = update.reset_period
                t["is_active"] = update.is_active
                found = True
                break
                
        if not found:
            data["tenants"].append({
                "id": tenant_id,
                "max_tokens": update.max_tokens,
                "reset_period": update.reset_period,
                "is_active": update.is_active
            })
            
        # Write back to file
        with open(quota_file, "w") as f:
            yaml.safe_dump(data, f, default_flow_style=False, sort_keys=False)
            
        # Tell the quota service to reload from the file
        quota_svc._load_quotas()
        
        return {"status": "success", "message": f"Quota updated for {tenant_id}"}
        
    except Exception as e:
        logger.error(f"Failed to update quotas file: {e}")
        raise HTTPException(status_code=500, detail="Failed to save quotas configuration")
