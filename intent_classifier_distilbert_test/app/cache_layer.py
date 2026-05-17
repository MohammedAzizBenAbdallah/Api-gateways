"""Redis + in-process LRU cache (mirrors production; Redis optional for local runs)."""

from __future__ import annotations

import hashlib
import json
import logging
from collections import OrderedDict
from typing import Any

import redis.asyncio as redis

from app.schemas import ClassifyResponse

logger = logging.getLogger(__name__)


def _sha256_hex(parts: bytes) -> str:
    h = hashlib.sha256()
    h.update(parts)
    return h.hexdigest()


class ClassificationCache:
    def __init__(
        self,
        *,
        redis_url: str,
        redis_enabled: bool,
        model_id: str,
        labels_tuple: tuple[str, ...],
        fingerprint_hash: str,
        ttl_seconds: int,
        lru_max: int,
    ) -> None:
        self._redis_url = redis_url
        self._redis_enabled = redis_enabled and bool(redis_url.strip())
        self._fingerprint_hash = fingerprint_hash
        self._ttl = ttl_seconds
        self._lru: OrderedDict[str, ClassifyResponse] = OrderedDict()
        self._lru_max = max(1, lru_max)
        self._client: redis.Redis | None = None
        _ = labels_tuple  # included in fingerprint_hash by caller

    async def connect(self) -> None:
        if not self._redis_enabled:
            logger.info("Redis disabled; using in-process LRU cache only")
            return
        if self._client is None:
            self._client = redis.from_url(self._redis_url, decode_responses=True)

    async def close(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    def _cache_key(self, text_norm: str, tenant_id: str | None) -> str:
        th = _sha256_hex(text_norm.encode("utf-8"))
        tenant = (tenant_id or "default").strip() or "default"
        return f"intent:cls:v6:{self._fingerprint_hash}:{tenant}:{th}"

    def _lru_get(self, key: str) -> ClassifyResponse | None:
        val = self._lru.get(key)
        if val is None:
            return None
        self._lru.move_to_end(key)
        return val

    def _lru_set(self, key: str, response: ClassifyResponse) -> None:
        self._lru[key] = response
        self._lru.move_to_end(key)
        while len(self._lru) > self._lru_max:
            self._lru.popitem(last=False)

    async def get(self, text_norm: str, tenant_id: str | None) -> ClassifyResponse | None:
        ck = self._cache_key(text_norm, tenant_id)
        hit = self._lru_get(ck)
        if hit is not None:
            return ClassifyResponse(
                intent_label=hit.intent_label,
                confidence=hit.confidence,
                source="cache",
                taxonomy_version=hit.taxonomy_version,
                model_id=hit.model_id,
            )
        if self._client is None:
            return None
        try:
            raw = await self._client.get(ck)
        except Exception as exc:
            logger.warning("Redis get failed: %s", exc)
            return None
        if not raw:
            return None
        try:
            data: dict[str, Any] = json.loads(raw)
            resp = ClassifyResponse.model_validate(data)
            self._lru_set(ck, resp)
            return ClassifyResponse(
                intent_label=resp.intent_label,
                confidence=resp.confidence,
                source="cache",
                taxonomy_version=resp.taxonomy_version,
                model_id=resp.model_id,
            )
        except Exception:
            return None

    async def set(self, text_norm: str, response: ClassifyResponse, tenant_id: str | None) -> None:
        ck = self._cache_key(text_norm, tenant_id)
        to_store = ClassifyResponse(
            intent_label=response.intent_label,
            confidence=response.confidence,
            source=response.source,
            taxonomy_version=response.taxonomy_version,
            model_id=response.model_id,
        )
        self._lru_set(ck, to_store)
        if self._client is None:
            return
        try:
            await self._client.setex(ck, self._ttl, to_store.model_dump_json())
        except Exception as exc:
            logger.warning("Redis set failed: %s", exc)
