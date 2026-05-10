# app/api/admin/gateway_plugins.py
"""
Admin API router for Zero-Code Kong Edge Plugin management.

This module acts as a proxy layer between the React Admin UI and the Kong
Admin API. In hybrid mode the Admin API only lives on the control plane
(kong-cp), which is reachable from inside the docker network only. The
URL is overridable via the KONG_ADMIN_URL env var.
"""

import os
from fastapi import APIRouter, Depends, HTTPException, Request
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

KONG_ADMIN_URL = os.getenv("KONG_ADMIN_URL", "http://kong-cp:8001")
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

class AutoRegisterRequest(BaseModel):
    """Schema for one-click route registration."""
    path: str
    methods: List[str]
    name: Optional[str] = None
    service_id: Optional[str] = None


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
# Helpers: Flatten / Unflatten nested configs
# ──────────────────────────────────────────────

def flatten_dict(nested_dict: dict, prefix: str = "") -> dict:
    """Flattens a nested dictionary into a single-level dictionary with dot-notated keys."""
    flat = {}
    if not isinstance(nested_dict, dict):
        return flat
    for key, value in nested_dict.items():
        if isinstance(value, dict):
            flat.update(flatten_dict(value, prefix=f"{prefix}{key}."))
        else:
            flat[f"{prefix}{key}"] = value
    return flat

def unflatten_dict(flat_dict: dict) -> dict:
    """Converts a flat dictionary with dot-notated keys back into a nested structure for Kong."""
    nested = {}
    if not isinstance(flat_dict, dict):
        return nested
    for key, value in flat_dict.items():
        # Skip empty values to allow Kong to use its defaults
        if value == "" or value is None:
            continue
        parts = key.split(".")
        d = nested
        for part in parts[:-1]:
            if part not in d:
                d[part] = {}
            d = d[part]
        d[parts[-1]] = value
    return nested


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
            "config": flatten_dict(p.get("config", {})),
            "created_at": p.get("created_at"),
        })

    return result


@router.post("/plugins")
async def apply_plugin(req: PluginApplyRequest):
    """Apply a plugin globally or to a specific route/service."""
    payload: Dict[str, Any] = {
        "name": req.name,
        "config": unflatten_dict(req.config),
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
        payload["config"] = unflatten_dict(req.config)
    if req.enabled is not None:
        payload["enabled"] = req.enabled

    result = await _kong_request("PATCH", f"/plugins/{plugin_id}", json_data=payload)
    return {"status": "success", "message": "Plugin updated", "data": result}


@router.delete("/plugins/{plugin_id}")
async def delete_plugin(plugin_id: str):
    """Remove a plugin entirely."""
    await _kong_request("DELETE", f"/plugins/{plugin_id}")
    return {"status": "success", "message": "Plugin removed"}


import asyncio

# ──────────────────────────────────────────────
# Plugin Metadata for UI Enrichment
# ──────────────────────────────────────────────

PLUGIN_METADATA = {
    "rate-limiting": {"label": "🚦 Rate Limiting", "category": "traffic"},
    "ip-restriction": {"label": "🚫 IP Restriction", "category": "security"},
    "cors": {"label": "🌍 CORS", "category": "traffic"},
    "key-auth": {"label": "🗝️ API Key Authentication", "category": "auth"},
    "basic-auth": {"label": "🔐 Basic Authentication", "category": "auth"},
    "oauth2": {"label": "🔓 OAuth 2.0", "category": "auth"},
    "hmac-auth": {"label": "✏️ HMAC Authentication", "category": "auth"},
    "http-log": {"label": "📝 HTTP Log", "category": "logging"},
    "file-log": {"label": "📄 File Log", "category": "logging"},
    "correlation-id": {"label": "🔗 Correlation ID", "category": "logging"},
    "opentelemetry": {"label": "📡 OpenTelemetry", "category": "logging"},
    "prometheus": {"label": "📈 Prometheus Metrics", "category": "logging"},
    "request-transformer": {"label": "🔧 Request Transformer", "category": "transformation"},
    "response-transformer": {"label": "🔧 Response Transformer", "category": "transformation"},
    "pre-function": {"label": "🧩 Pre-function (Custom Lua)", "category": "transformation"},
    "post-function": {"label": "🧩 Post-function (Custom Lua)", "category": "transformation"},
    "ai-proxy": {"label": "🤖 AI Proxy", "category": "ai"},
    "ai-prompt-guard": {"label": "🛡️ AI Prompt Guard", "category": "security"},
    "ai-prompt-decorator": {"label": "✨ AI Prompt Decorator", "category": "ai"},
}

def flatten_schema(schema: dict, prefix: str = "") -> list:
    """Recursively flattens Kong's nested plugin schema into a flat UI form field array."""
    fields = []
    if not isinstance(schema, dict) or "fields" not in schema:
        return fields
    
    for field_obj in schema["fields"]:
        for key, details in field_obj.items():
            if details.get("type") == "record" and "fields" in details:
                # Recursively flatten nested config objects (like `redis.host`)
                fields.extend(flatten_schema(details, prefix=f"{prefix}{key}."))
            else:
                field_type = "text"
                if details.get("type") == "boolean":
                    field_type = "boolean"
                elif details.get("type") in ["number", "integer"]:
                    field_type = "number"
                elif details.get("type") == "array":
                    field_type = "text" # Fallback to text for arrays
                
                fields.append({
                    "key": f"{prefix}{key}",
                    "label": f"{prefix}{key}",
                    "type": field_type,
                    "default": details.get("default", ""),
                    "required": details.get("required", False),
                    "description": details.get("description", "")
                })
    return fields

@router.get("/plugin-catalog")
async def get_plugin_catalog():
    """Dynamically fetch all available plugins and their schemas directly from Kong."""
    root_data = await _kong_request("GET", "/")
    available_plugins = list(root_data.get("plugins", {}).get("available_on_server", {}).keys())
    
    async def fetch_and_parse(plugin_name: str):
        try:
            schema = await _kong_request("GET", f"/plugins/schema/{plugin_name}")
            metadata = PLUGIN_METADATA.get(plugin_name, {"label": f"🔌 {plugin_name}", "category": "other"})
            return {
                "name": plugin_name,
                "label": metadata["label"],
                "description": schema.get("description", f"Automatically discovered Kong plugin: {plugin_name}"),
                "category": metadata["category"],
                "fields": flatten_schema(schema)
            }
        except Exception as e:
            logger.warning(f"Failed to parse schema for plugin {plugin_name}: {e}")
            return None

    # Concurrently fetch schemas for all discovered plugins
    tasks = [fetch_and_parse(p) for p in available_plugins]
    results = await asyncio.gather(*tasks)
    
    catalog = [r for r in results if r is not None]
    
    # Sort output: Custom Categories first, then alphabetical
    category_order = {"traffic": 1, "security": 2, "auth": 3, "ai": 4, "logging": 5, "transformation": 6, "other": 7}
    catalog.sort(key=lambda x: (category_order.get(x["category"], 99), x["name"]))
    
    return catalog

# ──────────────────────────────────────────────
# Intelligent Route Discovery Endpoints
# ──────────────────────────────────────────────

@router.get("/route-discovery")
async def route_discovery(request: Request):
    """Scan FastAPI schema and cross-reference with Kong Gateway routes."""
    # 1. Introspect FastAPI
    openapi_schema = request.app.openapi()
    fastapi_paths = []
    for path, path_item in openapi_schema.get("paths", {}).items():
        methods = [method.upper() for method in path_item.keys()]
        tags = []
        for method_obj in path_item.values():
            if "tags" in method_obj:
                tags.extend(method_obj["tags"])
        fastapi_paths.append({
            "path": path,
            "methods": methods,
            "tags": list(set(tags))
        })
        
    # 2. Fetch Kong Routes
    kong_routes_resp = await _kong_request("GET", "/routes")
    kong_routes = kong_routes_resp.get("data", [])
    
    # Fetch all plugins globally and filter by route.id
    kong_plugins_resp = await _kong_request("GET", "/plugins")
    kong_plugins = kong_plugins_resp.get("data", [])
    
    plugins_by_route = {}
    for p in kong_plugins:
        if "route" in p and p["route"] is not None and "id" in p["route"]:
            rid = p["route"]["id"]
            if rid not in plugins_by_route:
                plugins_by_route[rid] = []
            plugins_by_route[rid].append(p)
            
    # Helper to check if a path matches a Kong route
    def find_kong_route(api_path: str):
        for kr in kong_routes:
            for kp in kr.get("paths", []):
                # Match exact or prefix
                if api_path.startswith(kp) or api_path == kp:
                    return kr
        return None

    # 3. Cross-reference
    results = []
    matched_kong_routes = set()
    
    for fp in fastapi_paths:
        kr = find_kong_route(fp["path"])
        if kr:
            matched_kong_routes.add(kr["id"])
            route_plugins = plugins_by_route.get(kr["id"], [])
            
            # Determine status based on presence of plugins
            status = "protected" if route_plugins else "registered"
            
            results.append({
                "path": fp["path"],
                "methods": fp["methods"],
                "tags": fp["tags"],
                "status": status,
                "kong_route": kr.get("name", kr["id"]),
                "kong_route_id": kr["id"],
                "plugins": [p["name"] for p in route_plugins]
            })
        else:
            status = "exposed"
            results.append({
                "path": fp["path"],
                "methods": fp["methods"],
                "tags": fp["tags"],
                "status": status,
                "kong_route": None,
                "kong_route_id": None,
                "plugins": []
            })
            
    # Kong-only routes
    kong_only = []
    for kr in kong_routes:
        if kr["id"] not in matched_kong_routes:
            route_plugins = plugins_by_route.get(kr["id"], [])
            kong_only.append({
                "id": kr["id"],
                "name": kr.get("name", kr["id"]),
                "paths": kr.get("paths", []),
                "plugins": [p["name"] for p in route_plugins]
            })
            
    coverage = 0
    if len(results) > 0:
        protected_count = sum(1 for r in results if r["status"] in ["protected", "registered"])
        coverage = int((protected_count / len(results)) * 100)

    # Sort results to have exposed routes at the top, then registered, then protected
    status_order = {"exposed": 0, "registered": 1, "protected": 2}
    results.sort(key=lambda x: (status_order.get(x["status"], 99), x["path"]))

    return {
        "total_backend_paths": len(results),
        "total_kong_routes": len(kong_routes),
        "coverage_percent": coverage,
        "paths": results,
        "kong_only_routes": kong_only
    }

@router.post("/auto-register")
async def auto_register(req: AutoRegisterRequest):
    """Automatically register an exposed path in Kong."""
    services_resp = await _kong_request("GET", "/services")
    services = services_resp.get("data", [])
    
    target_service_id = req.service_id
    if not target_service_id:
        # Try to find a service that looks like the backend
        for s in services:
            if "fastapi" in s.get("name", "").lower():
                target_service_id = s["id"]
                break
                
    if not target_service_id and services:
        target_service_id = services[0]["id"] # Fallback
        
    if not target_service_id:
        raise HTTPException(status_code=400, detail="No Kong services found to bind the route to.")
        
    route_name = req.name
    if not route_name:
        # Generate a name from the path: e.g. /api/admin/metrics -> api-admin-metrics
        clean_path = req.path.strip("/").replace("/", "-")
        route_name = f"auto-{clean_path}" if clean_path else "auto-root"
        
    payload = {
        "name": route_name,
        "paths": [req.path],
        "methods": req.methods,
        "service": {"id": target_service_id},
        "strip_path": False
    }
    
    result = await _kong_request("POST", "/routes", json_data=payload)
    return {"status": "success", "message": f"Route {route_name} registered.", "data": result}
