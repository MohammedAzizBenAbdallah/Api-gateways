# fastapi_backend/tests/unit/test_intent_cache.py
"""Unit tests for IntentCacheService."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any, List

import pytest

from app.core.exceptions import IntentNotFoundError
from app.services.intent_cache_service import IntentCacheService


@dataclass
class FakeMapping:
    intent_name: str
    service_id: str
    taxonomy_version: str


class FakeAsyncSessionContext:
    def __init__(self) -> None:
        self.session = object()

    async def __aenter__(self) -> Any:
        return self.session

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None


def fake_session_factory() -> FakeAsyncSessionContext:
    return FakeAsyncSessionContext()


def test_resolve_intent_success(monkeypatch: Any) -> None:
    async def _run() -> None:
        service = IntentCacheService(session_factory=fake_session_factory, refresh_interval_seconds=30.0)

        async def fake_list_active_intent_mappings(session: Any) -> List[FakeMapping]:
            _ = session
            return [
                FakeMapping(intent_name="general_chat", service_id="ollama_llama3.2", taxonomy_version="1.0.0"),
                FakeMapping(intent_name="code_generation", service_id="ollama_deep_seek_coder", taxonomy_version="1.0.0"),
            ]

        # Patch the imported symbol inside the intent_cache_service module.
        monkeypatch.setattr(
            "app.services.intent_cache_service.list_active_intent_mappings",
            fake_list_active_intent_mappings,
        )

        await service.force_reload(session=object())
        assert service.resolve_intent("general_chat") == "ollama_llama3.2"

    asyncio.run(_run())


def test_resolve_intent_unknown_raises() -> None:
    service = IntentCacheService(session_factory=fake_session_factory, refresh_interval_seconds=30.0)
    service._cache = {}  # type: ignore[attr-defined]
    service._version = "2.1.0"  # type: ignore[attr-defined]

    with pytest.raises(IntentNotFoundError) as excinfo:
        service.resolve_intent("missing_intent")

    assert excinfo.value.intent_name == "missing_intent"
    assert excinfo.value.taxonomy_version == "2.1.0"


def test_background_refresh_cancels_cleanly(monkeypatch: Any) -> None:
    async def _run() -> None:
        service = IntentCacheService(session_factory=fake_session_factory, refresh_interval_seconds=10.0)

        async def fake_force_reload(session: Any) -> None:
            _ = session
            return

        monkeypatch.setattr(service, "force_reload", fake_force_reload)

        task = asyncio.create_task(service.start_background_refresh())
        await asyncio.sleep(0.01)
        task.cancel()

        with pytest.raises(asyncio.CancelledError):
            await task

    asyncio.run(_run())

