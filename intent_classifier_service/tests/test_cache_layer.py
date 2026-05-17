"""Regression tests for ClassificationCache keying and hit behavior."""

from __future__ import annotations

import asyncio

from app.cache_layer import ClassificationCache
from app.schemas import ClassifyResponse


def _cache() -> ClassificationCache:
    return ClassificationCache(
        redis_url="redis://127.0.0.1:6379/15",
        model_id="test-model",
        labels_tuple=("general_chat", "code_generation"),
        system_instruction_hash="abc123",
        ttl_seconds=60,
        lru_max=32,
    )


def test_different_prompts_cold_miss() -> None:
    async def _run() -> None:
        cache = _cache()
        r1 = ClassifyResponse(
            intent_label="general_chat",
            confidence=0.9,
            source="model",
            taxonomy_version="1",
            model_id="test-model",
        )
        r2 = ClassifyResponse(
            intent_label="code_generation",
            confidence=0.85,
            source="model",
            taxonomy_version="1",
            model_id="test-model",
        )
        await cache.set("hello world", r1, "tenant-a")
        await cache.set("fix my react bug", r2, "tenant-a")

        hit1 = await cache.get("hello world", "tenant-a")
        hit2 = await cache.get("fix my react bug", "tenant-a")

        assert hit1 is not None and hit1.source == "cache"
        assert hit2 is not None and hit2.source == "cache"
        assert hit1.intent_label == "general_chat"
        assert hit2.intent_label == "code_generation"

    asyncio.run(_run())


def test_same_prompt_second_call_cache_hit() -> None:
    async def _run() -> None:
        cache = _cache()
        text = "Say hello in one sentence."
        stored = ClassifyResponse(
            intent_label="general_chat",
            confidence=0.92,
            source="model",
            taxonomy_version="1",
            model_id="test-model",
        )
        await cache.set(text, stored, "tenant-a")

        hit = await cache.get(text, "tenant-a")
        assert hit is not None
        assert hit.source == "cache"
        assert hit.intent_label == "general_chat"

    asyncio.run(_run())


def test_same_text_different_tenant_different_keys() -> None:
    async def _run() -> None:
        cache = _cache()
        text = "Fix this bug: my React useEffect runs twice."
        await cache.set(
            text,
            ClassifyResponse(
                intent_label="code_generation",
                confidence=0.88,
                source="model",
                taxonomy_version="1",
                model_id="test-model",
            ),
            "tenant-a",
        )
        await cache.set(
            text,
            ClassifyResponse(
                intent_label="general_chat",
                confidence=0.7,
                source="model",
                taxonomy_version="1",
                model_id="test-model",
            ),
            "tenant-b",
        )

        a = await cache.get(text, "tenant-a")
        b = await cache.get(text, "tenant-b")

        assert a is not None and a.intent_label == "code_generation"
        assert b is not None and b.intent_label == "general_chat"

    asyncio.run(_run())


def test_cache_key_prefix_includes_fingerprint() -> None:
    cache = _cache()
    key = cache._cache_key("normalized text", "tenant-a")
    assert key.startswith("intent:cls:v6:")
    assert key.count(":") >= 5
