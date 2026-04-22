"""Shared async Redis client for gateway nonce replay protection and tenant config."""

from __future__ import annotations

import asyncio
import logging
from typing import Optional

import redis.asyncio as redis

from app.core.config import settings

logger = logging.getLogger(__name__)

_lock = asyncio.Lock()
_client: Optional[redis.Redis] = None


async def get_shared_redis() -> redis.Redis:
    """Lazily construct a single Redis connection pool."""
    global _client
    async with _lock:
        if _client is None:
            _client = redis.from_url(settings.redis_url, decode_responses=True)
            logger.info("Initialized shared Redis client")
        return _client
