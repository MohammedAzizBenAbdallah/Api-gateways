# app/core/middleware.py
"""HTTP request middleware implemented as a FastAPI dependency."""

from __future__ import annotations

import logging

from fastapi import HTTPException, Request

from app.core.config import settings

logger = logging.getLogger(__name__)


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

