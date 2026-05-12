# app/core/middleware.py
"""HTTP request middleware: Kong verification, Correlation ID, and Security Headers.

This module provides:
1. verify_kong_header — FastAPI dependency that rejects non-Kong traffic.
2. CorrelationIdMiddleware — ASGI middleware that reads/generates a unique
   request ID and attaches it to logs and response headers.
3. SecurityHeadersMiddleware — ASGI middleware that injects OWASP-recommended
   security headers into every HTTP response.
"""

from __future__ import annotations

import logging
import uuid
from contextvars import ContextVar

from fastapi import HTTPException, Request
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response

from app.core.config import settings

logger = logging.getLogger(__name__)


# ── Context Variable for Correlation ID ─────────────────────────────────────
# This allows any code (including log filters) to access the current
# request's correlation ID without passing it explicitly.
correlation_id_ctx: ContextVar[str] = ContextVar("correlation_id", default="-")


# ── Kong Header Verification (FastAPI Dependency) ───────────────────────────

def verify_kong_header(request: Request) -> None:
    """Reject requests that are not coming from Kong gateway."""

    if request.method == "OPTIONS":
        return

    header_value = request.headers.get("kong-header")
    if header_value is None:
        raise HTTPException(status_code=403, detail="all requests should come from kong gateway")

    # If you set KONG_HEADER_VALUE, enforce it; otherwise accept any truthy header value.
    if settings.kong_header_value is not None and settings.kong_header_value != "true":
        if header_value != settings.kong_header_value:
            raise HTTPException(status_code=403, detail="all requests should come from kong gateway")

    return


# ── Correlation ID Middleware ───────────────────────────────────────────────

class CorrelationIdMiddleware(BaseHTTPMiddleware):
    """Reads or generates a unique Correlation ID for every request.

    Flow:
    1. Check for X-Correlation-ID header (injected by Kong's correlation-id plugin).
    2. If missing, generate a new UUID4.
    3. Store it in request.state and a ContextVar (for log access).
    4. Inject it into the response header so it propagates back to the client.
    """

    HEADER_NAME = "X-Correlation-ID"

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        # Read from Kong or generate a fresh one
        cid = request.headers.get(self.HEADER_NAME) or str(uuid.uuid4())

        # Store in request state (accessible by route handlers)
        request.state.correlation_id = cid

        # Store in ContextVar (accessible by logging filter)
        token = correlation_id_ctx.set(cid)

        try:
            response = await call_next(request)
        finally:
            correlation_id_ctx.reset(token)

        # Always echo the ID back in the response
        response.headers[self.HEADER_NAME] = cid
        return response


# ── Security Headers Middleware ─────────────────────────────────────────────

class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Injects OWASP-recommended security headers into every response.

    These headers protect against common web vulnerabilities:
    - Clickjacking (X-Frame-Options)
    - MIME sniffing (X-Content-Type-Options)
    - XSS (X-XSS-Protection)
    - Protocol downgrade (Strict-Transport-Security)
    - Referrer leakage (Referrer-Policy)
    - Permission policies (Permissions-Policy)
    """

    SECURITY_HEADERS = {
        "X-Content-Type-Options": "nosniff",
        "X-Frame-Options": "DENY",
        "X-XSS-Protection": "1; mode=block",
        "Strict-Transport-Security": "max-age=31536000; includeSubDomains",
        "Referrer-Policy": "strict-origin-when-cross-origin",
        "Permissions-Policy": "camera=(), microphone=(), geolocation=()",
    }

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        response = await call_next(request)
        for header, value in self.SECURITY_HEADERS.items():
            response.headers[header] = value
        return response
