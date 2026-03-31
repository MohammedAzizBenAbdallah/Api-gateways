# app/services/intent_cache_service.py
"""Hot-reloadable in-memory cache mapping intents to AI services."""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Callable, Dict, Optional, TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover
    from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import IntentNotFoundError
from app.repositories.intent_routing_repository import list_active_intent_mappings

logger = logging.getLogger(__name__)


SessionFactory = Callable[[], "AsyncSession"]


class IntentCacheService:
    """Maintain a cache of intent_name → service_id backed by the DB."""

    def __init__(
        self,
        *,
        session_factory: SessionFactory,
        refresh_interval_seconds: float = 30.0,
    ) -> None:
        self._session_factory = session_factory
        self._refresh_interval_seconds = refresh_interval_seconds
        self._cache: Dict[str, str] = {}
        self._version: str = "unknown"
        self._initialized = False

        self._reload_lock = asyncio.Lock()

    async def initialize(self) -> None:
        """Load the cache on startup."""
        async with self._reload_lock:
            async with self._session_factory() as session:
                await self.force_reload(session=session)
                self._initialized = True

    def resolve_intent(self, intent_name: str) -> str:
        """Resolve an intent name to a service_id or raise IntentNotFoundError."""
        service_id = self._cache.get(intent_name)
        if not service_id:
            raise IntentNotFoundError(intent_name=intent_name, taxonomy_version=self._version)
        return service_id

    @property
    def version(self) -> str:
        return self._version

    async def force_reload(self, *, session: "AsyncSession") -> None:
        """Reload all active mappings from the DB into memory."""
        mappings = await list_active_intent_mappings(session=session)

        new_cache: Dict[str, str] = {}
        latest_version = "unknown"
        for m in mappings:
            new_cache[m.intent_name] = m.service_id
            latest_version = m.taxonomy_version

        self._cache = new_cache
        self._version = latest_version
        logger.info(
            "[IntentCache] Loaded %d mappings (version: %s)",
            len(new_cache),
            self._version,
        )

    async def start_background_refresh(self) -> None:
        """Periodically refresh the cache until cancelled."""
        try:
            while True:
                async with self._reload_lock:
                    async with self._session_factory() as session:
                        await self.force_reload(session=session)
                await asyncio.sleep(self._refresh_interval_seconds)
        except asyncio.CancelledError:
            logger.info("[IntentCache] Background refresh cancelled")
            raise

