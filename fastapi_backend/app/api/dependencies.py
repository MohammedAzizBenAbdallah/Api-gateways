# app/api/dependencies.py
"""FastAPI dependency helpers for accessing application services."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import Request

from app.services.ai_request_service import AIRequestService

logger = logging.getLogger(__name__)


def get_ai_request_service(request: Request) -> AIRequestService:
    """Fetch the AIRequestService instance from app state."""
    return request.app.state.ai_request_service


def get_intent_cache_service(request: Request) -> Any:
    """Fetch the IntentCacheService instance from app state."""
    return request.app.state.intent_cache_service

