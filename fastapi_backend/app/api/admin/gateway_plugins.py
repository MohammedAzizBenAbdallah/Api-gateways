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
    # ── TRAFFIC CONTROL ──────────────────────────────────────────────────────
    {
        "name": "rate-limiting",
        "label": "🚦 Rate Limiting",
        "description": "Limit how many HTTP requests a client can make per time unit. Protects against abuse and DDoS attacks.",
        "category": "traffic",
        "fields": [
            {"key": "minute",  "label": "Requests per Minute", "type": "number", "default": 60,    "required": False},
            {"key": "hour",    "label": "Requests per Hour",   "type": "number", "default": 1000,  "required": False},
            {"key": "day",     "label": "Requests per Day",    "type": "number", "default": 10000, "required": False},
            {"key": "policy",  "label": "Counter Storage",     "type": "select", "options": ["local", "redis", "cluster"], "default": "local", "required": False},
            {"key": "fault_tolerant", "label": "Fault Tolerant (ignore errors)", "type": "boolean", "default": True, "required": False},
        ],
    },
    {
        "name": "response-ratelimiting",
        "label": "📊 Response Rate Limiting",
        "description": "Rate limit based on a custom HTTP response header (e.g. X-Kong-Limit). Useful for credit-based APIs.",
        "category": "traffic",
        "fields": [
            {"key": "limits.sms.minute", "label": "SMS Credits per Minute", "type": "number", "default": 10, "required": False, "hint": "Sets X-RateLimit-Limit-Sms header"},
        ],
    },
    {
        "name": "request-size-limiting",
        "label": "📦 Request Size Limit",
        "description": "Block requests with payloads larger than a specified size. Prevents large payload attacks.",
        "category": "traffic",
        "fields": [
            {"key": "allowed_payload_size", "label": "Max Payload Size (MB)", "type": "number", "default": 8, "required": True},
            {"key": "size_unit", "label": "Unit", "type": "select", "options": ["megabytes", "kilobytes", "bytes"], "default": "megabytes", "required": False},
        ],
    },
    {
        "name": "proxy-cache",
        "label": "⚡ Proxy Cache",
        "description": "Cache and serve responses at the Kong layer to reduce load on your AI backend.",
        "category": "traffic",
        "fields": [
            {"key": "response_code",   "label": "Cache HTTP Status Codes (comma-separated)", "type": "text",   "default": "200,301,404", "required": True, "hint": "e.g. 200,301"},
            {"key": "request_method",  "label": "Cache HTTP Methods (comma-separated)",      "type": "text",   "default": "GET,HEAD",    "required": True},
            {"key": "content_type",    "label": "Cache Content Types (comma-separated)",      "type": "text",   "default": "application/json",  "required": False},
            {"key": "cache_ttl",       "label": "Cache TTL (seconds)",                         "type": "number", "default": 300,           "required": False},
        ],
    },
    {
        "name": "redirect",
        "label": "↩️ Redirect",
        "description": "Redirect incoming requests to another URL with a configurable HTTP status code.",
        "category": "traffic",
        "fields": [
            {"key": "location",    "label": "Redirect Location URL", "type": "text",   "default": "https://example.com", "required": True},
            {"key": "status_code", "label": "HTTP Status Code",       "type": "number", "default": 301,                   "required": False},
        ],
    },

    # ── SECURITY ─────────────────────────────────────────────────────────────
    {
        "name": "cors",
        "label": "🌐 CORS Control",
        "description": "Control which external websites can call your API. Prevents unauthorized cross-origin requests.",
        "category": "security",
        "fields": [
            {"key": "origins",     "label": "Allowed Origins (comma-separated)",      "type": "text",    "default": "*",                               "required": True,  "hint": "e.g. https://example.com"},
            {"key": "methods",     "label": "Allowed HTTP Methods (comma-separated)", "type": "text",    "default": "GET,POST,PUT,DELETE,OPTIONS",      "required": False},
            {"key": "headers",     "label": "Allowed Headers (comma-separated)",      "type": "text",    "default": "Authorization,Content-Type",       "required": False},
            {"key": "credentials", "label": "Allow Credentials",                      "type": "boolean", "default": True,                               "required": False},
            {"key": "max_age",     "label": "Cache Duration (seconds)",               "type": "number",  "default": 3600,                              "required": False},
        ],
    },
    {
        "name": "ip-restriction",
        "label": "🔒 IP Restriction",
        "description": "Block or allow traffic from specific IP addresses or CIDR ranges.",
        "category": "security",
        "fields": [
            {"key": "allow", "label": "Allowed IPs (comma-separated)", "type": "text", "default": "", "required": False, "hint": "e.g. 192.168.1.0/24, 10.0.0.1"},
            {"key": "deny",  "label": "Blocked IPs (comma-separated)", "type": "text", "default": "", "required": False, "hint": "e.g. 1.2.3.4, 5.6.7.0/24"},
        ],
    },
    {
        "name": "bot-detection",
        "label": "🤖 Bot Detection",
        "description": "Automatically detect and block known malicious bots and crawlers.",
        "category": "security",
        "fields": [
            {"key": "allow", "label": "Allowed Bot User-Agents (comma-separated)", "type": "text", "default": "", "required": False, "hint": "Leave empty to use Kong defaults"},
            {"key": "deny",  "label": "Blocked Bot User-Agents (comma-separated)", "type": "text", "default": "", "required": False, "hint": "Leave empty to use Kong defaults"},
        ],
    },
    {
        "name": "request-termination",
        "label": "🚫 Block Route",
        "description": "Instantly block all traffic to a specific route. Use for maintenance or emergency lockdowns.",
        "category": "security",
        "fields": [
            {"key": "status_code", "label": "HTTP Status Code", "type": "number", "default": 503,                                       "required": True},
            {"key": "message",     "label": "Block Message",     "type": "text",   "default": "This endpoint is under maintenance.",     "required": False},
        ],
    },
    {
        "name": "acl",
        "label": "👥 Access Control List (ACL)",
        "description": "Restrict route access to specific consumer groups. Requires authentication plugin.",
        "category": "security",
        "fields": [
            {"key": "allow", "label": "Allowed Groups (comma-separated)", "type": "text", "default": "",     "required": False, "hint": "e.g. admins, developers"},
            {"key": "deny",  "label": "Denied Groups (comma-separated)",  "type": "text", "default": "",     "required": False},
        ],
    },

    # ── AI PLUGINS ───────────────────────────────────────────────────────────
    {
        "name": "ai-prompt-guard",
        "label": "🛡️ AI Prompt Guard",
        "description": "Block or allow AI prompts based on regex patterns. Prevents prompt injection and jailbreak attacks at the gateway level.",
        "category": "ai",
        "fields": [
            {"key": "deny_patterns",  "label": "Deny Patterns (comma-separated regex)", "type": "text", "default": "", "required": False, "hint": "e.g. ignore previous instructions, DAN mode"},
            {"key": "allow_patterns", "label": "Allow Patterns (comma-separated regex)", "type": "text", "default": "", "required": False},
            {"key": "match_all_roles", "label": "Match All Message Roles", "type": "boolean", "default": False, "required": False},
        ],
    },
    {
        "name": "ai-proxy",
        "label": "🔀 AI Proxy",
        "description": "Route AI requests to OpenAI, Azure, Cohere, or Anthropic with a single unified interface.",
        "category": "ai",
        "fields": [
            {"key": "provider",             "label": "AI Provider",     "type": "select", "options": ["openai", "azure", "anthropic", "cohere", "mistral", "llama2"], "default": "openai", "required": True},
            {"key": "model.name",           "label": "Model Name",      "type": "text",   "default": "gpt-4",  "required": True, "hint": "e.g. gpt-4, claude-3-opus"},
            {"key": "auth.header_name",     "label": "Auth Header Name","type": "text",   "default": "Authorization", "required": False},
            {"key": "auth.header_value",    "label": "Auth Header Value","type": "text",  "default": "Bearer sk-...",  "required": False},
        ],
    },
    {
        "name": "ai-prompt-decorator",
        "label": "✏️ AI Prompt Decorator",
        "description": "Automatically prepend or append system instructions to every AI request. Enforce behavior without modifying the client.",
        "category": "ai",
        "fields": [
            {"key": "prompts.prepend", "label": "Prepend System Prompt", "type": "text", "default": "You are a helpful assistant.", "required": False},
            {"key": "prompts.append",  "label": "Append System Prompt",  "type": "text", "default": "",                             "required": False},
        ],
    },

    # ── AUTHENTICATION ────────────────────────────────────────────────────────
    {
        "name": "jwt",
        "label": "🔑 JWT Authentication",
        "description": "Validate JSON Web Tokens (JWT) on incoming requests. Works with Keycloak and other OIDC providers.",
        "category": "auth",
        "fields": [
            {"key": "key_claim_name",   "label": "Key Claim Name",    "type": "text",    "default": "iss",  "required": False},
            {"key": "claims_to_verify", "label": "Claims to Verify (comma-separated)", "type": "text", "default": "exp", "required": False},
            {"key": "uri_param_names",  "label": "URI Parameter Names","type": "text",   "default": "jwt",  "required": False},
            {"key": "cookie_names",     "label": "Cookie Names",       "type": "text",   "default": "",     "required": False},
        ],
    },
    {
        "name": "key-auth",
        "label": "🗝️ API Key Authentication",
        "description": "Require consumers to present a static API key in a header or query parameter.",
        "category": "auth",
        "fields": [
            {"key": "key_names",     "label": "Header / Query Param Name", "type": "text",    "default": "apikey", "required": True},
            {"key": "hide_credentials", "label": "Strip Key from Upstream", "type": "boolean", "default": True,    "required": False},
        ],
    },
    {
        "name": "basic-auth",
        "label": "🔐 Basic Authentication",
        "description": "Add Basic HTTP Authentication (username + password) to a route.",
        "category": "auth",
        "fields": [
            {"key": "hide_credentials", "label": "Strip Credentials from Upstream", "type": "boolean", "default": False, "required": False},
        ],
    },
    {
        "name": "oauth2",
        "label": "🔓 OAuth 2.0",
        "description": "Add OAuth 2.0 authorization server capabilities to your route (client credentials, password, implicit, authorization code).",
        "category": "auth",
        "fields": [
            {"key": "scopes",             "label": "Allowed Scopes (comma-separated)", "type": "text",    "default": "email,profile", "required": True},
            {"key": "mandatory_scope",    "label": "Enforce Scope",                    "type": "boolean", "default": True,            "required": False},
            {"key": "enable_client_credentials", "label": "Enable Client Credentials Flow", "type": "boolean", "default": True, "required": False},
            {"key": "enable_implicit_grant",     "label": "Enable Implicit Grant",          "type": "boolean", "default": False, "required": False},
        ],
    },
    {
        "name": "hmac-auth",
        "label": "✏️ HMAC Authentication",
        "description": "Authenticate requests using HMAC signature validation. For highly secure machine-to-machine communication.",
        "category": "auth",
        "fields": [
            {"key": "hide_credentials",     "label": "Strip HMAC Header from Upstream", "type": "boolean", "default": False, "required": False},
            {"key": "clock_skew",           "label": "Allowed Clock Skew (seconds)",     "type": "number",  "default": 300,   "required": False},
            {"key": "validate_request_body","label": "Validate Request Body Digest",     "type": "boolean", "default": False, "required": False},
        ],
    },

    # ── LOGGING ───────────────────────────────────────────────────────────────
    {
        "name": "http-log",
        "label": "📝 HTTP Log",
        "description": "Send request and response data to an HTTP endpoint as JSON. Already configured to feed the Kong Logger service.",
        "category": "logging",
        "fields": [
            {"key": "http_endpoint",  "label": "Log Receiver URL",    "type": "text",   "default": "http://kong-logger:9999/logs", "required": True},
            {"key": "method",         "label": "HTTP Method",          "type": "select", "options": ["POST", "PUT"], "default": "POST", "required": False},
            {"key": "content_type",   "label": "Content Type",         "type": "select", "options": ["application/json", "application/json; charset=utf-8"], "default": "application/json", "required": False},
            {"key": "timeout",        "label": "Connection Timeout (ms)","type": "number", "default": 10000, "required": False},
            {"key": "keepalive",      "label": "Keepalive (ms)",        "type": "number", "default": 60000, "required": False},
        ],
    },
    {
        "name": "file-log",
        "label": "📄 File Log",
        "description": "Append request and response logs to a file on disk. Useful for debugging.",
        "category": "logging",
        "fields": [
            {"key": "path",   "label": "File Path",        "type": "text",    "default": "/tmp/kong.log", "required": True},
            {"key": "reopen", "label": "Reopen File Daily","type": "boolean", "default": False,           "required": False},
        ],
    },
    {
        "name": "correlation-id",
        "label": "🔗 Correlation ID",
        "description": "Automatic adds a unique X-Correlation-ID header to every request for distributed tracing.",
        "category": "logging",
        "fields": [
            {"key": "header_name",  "label": "Header Name",     "type": "text",   "default": "Kong-Request-ID", "required": False},
            {"key": "generator",    "label": "ID Generator",     "type": "select", "options": ["uuid", "uuid#counter", "tracker"], "default": "uuid", "required": False},
            {"key": "echo_downstream", "label": "Echo ID in Response", "type": "boolean", "default": False, "required": False},
        ],
    },
    {
        "name": "opentelemetry",
        "label": "📡 OpenTelemetry",
        "description": "Export distributed traces (spans) to an OpenTelemetry-compatible collector (Jaeger, Zipkin, Tempo).",
        "category": "logging",
        "fields": [
            {"key": "endpoint",         "label": "OTLP HTTP Endpoint", "type": "text",   "default": "http://otel-collector:4318/v1/traces", "required": True},
            {"key": "resource_attributes.service.name", "label": "Service Name", "type": "text", "default": "nextora-ai-gateway", "required": False},
            {"key": "sampling_rate",    "label": "Sampling Rate (0.0-1.0)", "type": "number", "default": 1.0, "required": False},
        ],
    },
    {
        "name": "prometheus",
        "label": "📈 Prometheus Metrics",
        "description": "Expose a /metrics endpoint for Prometheus to scrape. Powers your Grafana dashboards.",
        "category": "logging",
        "fields": [
            {"key": "status_code_metrics",  "label": "Track by Status Code",  "type": "boolean", "default": True,  "required": False},
            {"key": "latency_metrics",      "label": "Track Latency",          "type": "boolean", "default": True,  "required": False},
            {"key": "bandwidth_metrics",    "label": "Track Bandwidth",         "type": "boolean", "default": True,  "required": False},
            {"key": "upstream_health_metrics", "label": "Track Upstream Health","type": "boolean", "default": True,  "required": False},
            {"key": "per_consumer",         "label": "Track per Consumer",     "type": "boolean", "default": False, "required": False},
        ],
    },

    # ── TRANSFORMATION ────────────────────────────────────────────────────────
    {
        "name": "request-transformer",
        "label": "🔧 Request Transformer",
        "description": "Add, remove, or rename headers and query parameters from incoming requests before they reach the backend.",
        "category": "transformation",
        "fields": [
            {"key": "add.headers",    "label": "Add Headers (key:value, comma-sep.)",    "type": "text", "default": "", "required": False, "hint": "e.g. X-Source:Kong, X-Env:prod"},
            {"key": "remove.headers", "label": "Remove Headers (comma-separated)",        "type": "text", "default": "", "required": False, "hint": "e.g. X-Internal-Token"},
            {"key": "add.querystring","label": "Add Query Params (key:value, comma-sep.)","type": "text", "default": "", "required": False},
        ],
    },
    {
        "name": "response-transformer",
        "label": "🔧 Response Transformer",
        "description": "Add, remove, or rename headers from your backend's responses before they reach the client.",
        "category": "transformation",
        "fields": [
            {"key": "add.headers",    "label": "Add Response Headers (key:value, comma-sep.)",   "type": "text", "default": "", "required": False, "hint": "e.g. X-Powered-By:Nextora"},
            {"key": "remove.headers", "label": "Remove Response Headers (comma-separated)",       "type": "text", "default": "", "required": False, "hint": "e.g. Server, X-Powered-By"},
        ],
    },
    {
        "name": "pre-function",
        "label": "🧩 Pre-function (Custom Lua)",
        "description": "Execute a custom Lua snippet at the start of the request lifecycle. For advanced gateway programmability.",
        "category": "transformation",
        "fields": [
            {"key": "access", "label": "Lua Code (access phase)", "type": "text", "default": "-- kong.log.notice('Hello from pre-function')", "required": False},
        ],
    },
    {
        "name": "post-function",
        "label": "🧩 Post-function (Custom Lua)",
        "description": "Execute a custom Lua snippet at the end of the request lifecycle, after the response is received.",
        "category": "transformation",
        "fields": [
            {"key": "access", "label": "Lua Code (access phase)", "type": "text", "default": "-- kong.log.notice('Hello from post-function')", "required": False},
        ],
    },
]


@router.get("/plugin-catalog")
async def get_plugin_catalog():
    """Returns the list of available plugins with their UI field definitions."""
    return PLUGIN_CATALOG
