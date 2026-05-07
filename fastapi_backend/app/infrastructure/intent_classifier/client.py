"""Async HTTP client for POST /classify on the intent classifier service."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

import httpx

from app.core.config import settings
from app.intent_classification.contract import UNCLASSIFIED_LABEL, load_taxonomy_v1

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ClassifierDecision:
    intent_label: str
    confidence: float
    source: str


class IntentClassifierClient:
    def __init__(
        self,
        *,
        base_url: str | None = None,
        timeout_seconds: float | None = None,
        enabled: bool | None = None,
    ) -> None:
        self._base = (base_url or settings.intent_classifier_url or "").rstrip("/")
        self._timeout = timeout_seconds if timeout_seconds is not None else settings.intent_classifier_timeout_seconds
        self._enabled = enabled if enabled is not None else settings.intent_classifier_enabled

    @property
    def is_configured(self) -> bool:
        return bool(self._base) and self._enabled

    async def classify(
        self,
        *,
        text: str,
        tenant_id: str | None,
        environment: str | None,
    ) -> ClassifierDecision:
        """Call classifier; on any failure return unclassified with confidence 0."""
        if not self.is_configured:
            return ClassifierDecision(
                intent_label=UNCLASSIFIED_LABEL,
                confidence=0.0,
                source="fallback",
            )
        taxonomy = load_taxonomy_v1(settings.intent_taxonomy_path or None)
        url = f"{self._base}/classify"
        payload: dict[str, Any] = {"text": text}
        if tenant_id:
            payload["tenant_id"] = tenant_id
        if environment:
            payload["environment"] = environment
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.post(url, json=payload)
                resp.raise_for_status()
                data = resp.json()
        except Exception as exc:
            logger.warning("Intent classifier request failed: %s", exc)
            return ClassifierDecision(
                intent_label=UNCLASSIFIED_LABEL,
                confidence=0.0,
                source="fallback",
            )

        label = str(data.get("intent_label", UNCLASSIFIED_LABEL))
        conf = float(data.get("confidence", 0.0))
        src = str(data.get("source", "model"))

        if label not in taxonomy.routable_labels:
            label = UNCLASSIFIED_LABEL
        return ClassifierDecision(intent_label=label, confidence=conf, source=src)
