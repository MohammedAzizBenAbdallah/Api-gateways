# app/core/error_handlers.py
"""Global exception handlers for standardized API error responses.

Every error returned by the platform follows a consistent JSON envelope:

    {
        "error": {
            "code": "QUOTA_EXCEEDED",
            "message": "Daily token quota exceeded for tenant-a",
            "request_id": "a1b2c3d4-...",
            "timestamp": "2026-05-12T13:00:00Z"
        }
    }

This ensures frontend clients can always parse errors predictably.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Dict

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.core.exceptions import (
    DomainError,
    IntentMappingAlreadyExistsError,
    IntentMappingNotFoundError,
    IntentNotFoundError,
    PolicyEvaluationError,
    PolicySyncError,
    PolicyViolationError,
    ProviderError,
    QuotaExceededError,
    SecurityViolationError,
    ServiceNotFoundError,
    TenantIdMissingError,
    TenantNotAuthorizedError,
)

logger = logging.getLogger(__name__)


def _build_error_response(
    *,
    status_code: int,
    code: str,
    message: str,
    request: Request,
    extra: Dict[str, Any] | None = None,
) -> JSONResponse:
    """Build a standardized error JSON response."""
    correlation_id = getattr(request.state, "correlation_id", None)

    body: Dict[str, Any] = {
        "error": {
            "code": code,
            "message": message,
            "request_id": correlation_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }
    }
    if extra:
        body["error"].update(extra)

    return JSONResponse(status_code=status_code, content=body)


# ── Exception → HTTP status mapping ─────────────────────────────────────────

_EXCEPTION_MAP: dict[type, tuple[int, str]] = {
    TenantIdMissingError: (401, "TENANT_ID_MISSING"),
    TenantNotAuthorizedError: (403, "TENANT_NOT_AUTHORIZED"),
    PolicyViolationError: (403, "POLICY_VIOLATION"),
    SecurityViolationError: (400, "SECURITY_VIOLATION"),
    QuotaExceededError: (429, "QUOTA_EXCEEDED"),
    IntentNotFoundError: (404, "INTENT_NOT_FOUND"),
    ServiceNotFoundError: (404, "SERVICE_NOT_FOUND"),
    IntentMappingNotFoundError: (404, "MAPPING_NOT_FOUND"),
    IntentMappingAlreadyExistsError: (409, "INTENT_ALREADY_EXISTS"),
    ProviderError: (502, "PROVIDER_ERROR"),
    PolicySyncError: (503, "POLICY_SYNC_ERROR"),
    PolicyEvaluationError: (503, "POLICY_EVALUATION_ERROR"),
}


async def domain_exception_handler(request: Request, exc: DomainError) -> JSONResponse:
    """Handle all DomainError subclasses with structured responses."""
    exc_type = type(exc)
    status_code, code = _EXCEPTION_MAP.get(exc_type, (500, "INTERNAL_ERROR"))

    extra = {}
    # Enrich specific exceptions with additional metadata
    if isinstance(exc, PolicyViolationError):
        extra["description"] = exc.description
        if exc.detected_pii_types:
            extra["detected_pii_types"] = exc.detected_pii_types
            extra["pii_count"] = exc.pii_count
    elif isinstance(exc, SecurityViolationError):
        extra["matched_patterns"] = exc.matched_patterns
        extra["score"] = exc.score

    logger.warning(
        "[ErrorHandler] %s → HTTP %d: %s",
        code,
        status_code,
        str(exc),
    )

    return _build_error_response(
        status_code=status_code,
        code=code,
        message=str(exc),
        request=request,
        extra=extra,
    )


async def generic_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Catch-all for unhandled exceptions — never leak stack traces."""
    logger.exception("[ErrorHandler] Unhandled exception: %s", exc)

    return _build_error_response(
        status_code=500,
        code="INTERNAL_SERVER_ERROR",
        message="An unexpected error occurred. Please contact support.",
        request=request,
    )


def register_error_handlers(app: FastAPI) -> None:
    """Register all exception handlers on the FastAPI app instance."""
    app.add_exception_handler(DomainError, domain_exception_handler)
    app.add_exception_handler(Exception, generic_exception_handler)
