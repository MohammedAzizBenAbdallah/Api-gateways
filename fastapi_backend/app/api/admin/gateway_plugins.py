# app/api/admin/gateway_plugins.py
"""
Admin API router for Zero-Code Kong Edge Plugin management.

This module acts as a proxy layer between the React Admin UI and the Kong
Admin API (http://kong-gateway:8001). It translates simple UI actions into
proper Kong plugin lifecycle operations, allowing non-technical administrators
to manage gateway security without writing YAML or using the terminal.
"""

from fastapi import APIRouter, Depends, HTTPException
import httpx
import logging
from pydantic import BaseModel
from typing import Optional, List, Dict, Any

from app.core.middleware import verify_kong_header

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/admin/gateway",
    tags=["Admin - Edge Security"],
    dependencies=[Depends(verify_kong_header)]
)

KONG_ADMIN_URL = "http://kong-gateway:8001"
KONG_TIMEOUT = 10.0

# ──────────────────────────────────────────────
# Pydantic Schemas
# ──────────────────────────────────────────────

class PluginApplyRequest(BaseModel):
    """Generic schema to apply any Kong plugin."""
    name: str                              # e.g. "rate-limiting", "ip-restriction"
    config: Dict[str, Any]                 # Plugin-specific config
    route_id: Optional[str] = None         # If None → global plugin
    service_id: Optional[str] = None       # If None → not scoped to service
    enabled: bool = True

class PluginUpdateRequest(BaseModel):
    """Schema to update an existing plugin."""
    config: Optional[Dict[str, Any]] = None
    enabled: Optional[bool] = None


# ──────────────────────────────────────────────
# Helper: reusable httpx client
# ──────────────────────────────────────────────

async def _kong_request(method: str, path: str, json_data: dict = None) -> dict:
    """Execute a request against the Kong Admin API."""
    try:
        async with httpx.AsyncClient(timeout=KONG_TIMEOUT) as client:
            resp = await client.request(method, f"{KONG_ADMIN_URL}{path}", json=json_data)
            resp.raise_for_status()
            if resp.status_code == 204:
                return {"status": "deleted"}
            return resp.json()
    except httpx.HTTPStatusError as e:
        detail = e.response.text if e.response else str(e)
        logger.error(f"Kong Admin API error [{method} {path}]: {detail}")
        raise HTTPException(status_code=e.response.status_code, detail=f"Kong Error: {detail}")
    except httpx.RequestError as e:
        logger.error(f"Failed to connect to Kong [{method} {path}]: {e}")
        raise HTTPException(status_code=502, detail="Cannot reach Kong Gateway. Is it running?")


# ──────────────────────────────────────────────
# Routes Endpoints
# ──────────────────────────────────────────────

@router.get("/routes")
async def list_routes():
    """List all Kong routes with their associated service info."""
    routes_data = await _kong_request("GET", "/routes")
    services_data = await _kong_request("GET", "/services")

    # Build a quick lookup: service_id → service object
    svc_map = {s["id"]: s for s in services_data.get("data", [])}

    result = []
    for route in routes_data.get("data", []):
        svc_id = route.get("service", {}).get("id") if route.get("service") else None
        svc = svc_map.get(svc_id, {})

        # Also fetch plugins scoped to this route
        route_plugins = await _kong_request("GET", f"/routes/{route['id']}/plugins")

        result.append({
            "id": route["id"],
            "name": route.get("name", "unnamed"),
            "paths": route.get("paths", []),
            "methods": route.get("methods"),
            "protocols": route.get("protocols", []),
            "service_name": svc.get("name", "unknown"),
            "service_url": f"{svc.get('protocol', 'http')}://{svc.get('host', '?')}:{svc.get('port', '?')}",
            "plugins": [
                {
                    "id": p["id"],
                    "name": p["name"],
                    "enabled": p["enabled"],
                    "config": p.get("config", {}),
                }
                for p in route_plugins.get("data", [])
            ],
        })

    return result


# ──────────────────────────────────────────────
# Plugins CRUD Endpoints
# ──────────────────────────────────────────────

@router.get("/plugins")
async def list_plugins():
    """List all active plugins (global + per-route)."""
    data = await _kong_request("GET", "/plugins")
    plugins = data.get("data", [])

    result = []
    for p in plugins:
        scope = "global"
        scope_target = None
        if p.get("route") and p["route"].get("id"):
            scope = "route"
            scope_target = p["route"]["id"]
        elif p.get("service") and p["service"].get("id"):
            scope = "service"
            scope_target = p["service"]["id"]

        result.append({
            "id": p["id"],
            "name": p["name"],
            "enabled": p["enabled"],
            "scope": scope,
            "scope_target": scope_target,
            "config": p.get("config", {}),
            "created_at": p.get("created_at"),
        })

    return result


@router.post("/plugins")
async def apply_plugin(req: PluginApplyRequest):
    """Apply a plugin globally or to a specific route/service."""
    payload: Dict[str, Any] = {
        "name": req.name,
        "config": req.config,
        "enabled": req.enabled,
    }
    if req.route_id:
        payload["route"] = {"id": req.route_id}
    if req.service_id:
        payload["service"] = {"id": req.service_id}

    result = await _kong_request("POST", "/plugins", json_data=payload)
    return {"status": "success", "message": f"Plugin '{req.name}' applied", "data": result}


@router.patch("/plugins/{plugin_id}")
async def update_plugin(plugin_id: str, req: PluginUpdateRequest):
    """Update an existing plugin's config or enabled state."""
    payload: Dict[str, Any] = {}
    if req.config is not None:
        payload["config"] = req.config
    if req.enabled is not None:
        payload["enabled"] = req.enabled

    result = await _kong_request("PATCH", f"/plugins/{plugin_id}", json_data=payload)
    return {"status": "success", "message": "Plugin updated", "data": result}


@router.delete("/plugins/{plugin_id}")
async def delete_plugin(plugin_id: str):
    """Remove a plugin entirely."""
    await _kong_request("DELETE", f"/plugins/{plugin_id}")
    return {"status": "success", "message": "Plugin removed"}


# ──────────────────────────────────────────────
# Plugin Catalog (static metadata for the UI)
# ──────────────────────────────────────────────

PLUGIN_CATALOG = [
    {
        "name": "rate-limiting",
        "label": "🚦 Rate Limiting",
        "description": "Limit how many requests a client can make per minute/hour. Protects against abuse and DDoS.",
        "category": "traffic",
        "fields": [
            {"key": "minute", "label": "Requests per Minute", "type": "number", "default": 60, "required": True},
            {"key": "hour", "label": "Requests per Hour", "type": "number", "default": 1000, "required": False},
            {"key": "policy", "label": "Counter Storage", "type": "select", "options": ["local", "redis"], "default": "local", "required": False},
        ],
    },
    {
        "name": "ip-restriction",
        "label": "🔒 IP Restriction",
        "description": "Block or allow traffic from specific IP addresses. Use for whitelisting trusted IPs or blacklisting attackers.",
        "category": "security",
        "fields": [
            {"key": "allow", "label": "Allowed IPs (comma-separated)", "type": "text", "default": "", "required": False, "hint": "e.g. 192.168.1.0/24, 10.0.0.1"},
            {"key": "deny", "label": "Blocked IPs (comma-separated)", "type": "text", "default": "", "required": False, "hint": "e.g. 1.2.3.4, 5.6.7.0/24"},
        ],
    },
    {
        "name": "cors",
        "label": "🌐 CORS Control",
        "description": "Control which external websites can call your API. Prevents unauthorized cross-origin requests.",
        "category": "security",
        "fields": [
            {"key": "origins", "label": "Allowed Origins (comma-separated)", "type": "text", "default": "*", "required": True, "hint": "e.g. https://example.com, http://localhost:3000"},
            {"key": "methods", "label": "Allowed HTTP Methods (comma-separated)", "type": "text", "default": "GET,POST,PUT,DELETE,OPTIONS", "required": False},
            {"key": "headers", "label": "Allowed Headers (comma-separated)", "type": "text", "default": "Authorization,Content-Type", "required": False},
            {"key": "credentials", "label": "Allow Credentials", "type": "boolean", "default": True, "required": False},
            {"key": "max_age", "label": "Cache Duration (seconds)", "type": "number", "default": 3600, "required": False},
        ],
    },
    {
        "name": "request-size-limiting",
        "label": "📦 Request Size Limit",
        "description": "Block requests with payloads larger than a specified size. Prevents large file upload attacks.",
        "category": "traffic",
        "fields": [
            {"key": "allowed_payload_size", "label": "Max Payload Size (MB)", "type": "number", "default": 8, "required": True},
        ],
    },
    {
        "name": "bot-detection",
        "label": "🤖 Bot Detection",
        "description": "Automatically block known malicious bots and web crawlers from accessing your API.",
        "category": "security",
        "fields": [
            {"key": "allow", "label": "Allowed Bot User-Agents (comma-separated)", "type": "text", "default": "", "required": False, "hint": "Leave empty to use defaults"},
            {"key": "deny", "label": "Blocked Bot User-Agents (comma-separated)", "type": "text", "default": "", "required": False, "hint": "Leave empty to use defaults"},
        ],
    },
    {
        "name": "request-termination",
        "label": "🚫 Block Route",
        "description": "Instantly block all traffic to a route. Useful for maintenance or shutting down compromised endpoints.",
        "category": "security",
        "fields": [
            {"key": "status_code", "label": "HTTP Status Code", "type": "number", "default": 403, "required": True},
            {"key": "message", "label": "Block Message", "type": "text", "default": "This endpoint is currently disabled by the administrator.", "required": False},
        ],
    },
    {
        "name": "acl",
        "label": "👥 Access Control List",
        "description": "Restrict route access to specific consumer groups. Only authenticated users in allowed groups can access.",
        "category": "auth",
        "fields": [
            {"key": "allow", "label": "Allowed Groups (comma-separated)", "type": "text", "default": "", "required": False, "hint": "e.g. admins, developers"},
            {"key": "deny", "label": "Denied Groups (comma-separated)", "type": "text", "default": "", "required": False},
        ],
    },
]


@router.get("/plugin-catalog")
async def get_plugin_catalog():
    """Returns the list of available plugins with their UI field definitions."""
    return PLUGIN_CATALOG
