"""Ollama-backed intent classification with structured JSON output."""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
from typing import Any

import httpx

from app.taxonomy import Taxonomy, UNCLASSIFIED

logger = logging.getLogger(__name__)

_FALLBACK_RESULT: dict[str, Any] = {
    "intent": UNCLASSIFIED,
    "confidence": 0.0,
    "reasoning": "llm_error",
    "multi_intent": [],
}

_RESPONSE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "intent": {"type": "string"},
        "confidence": {"type": "number"},
        "reasoning": {"type": "string"},
        "multi_intent": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["intent", "confidence", "reasoning", "multi_intent"],
}


def _hash_text_prefix(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def _build_system_instruction(taxonomy: Taxonomy) -> str:
    lines = ["Classify user text into one intent label from this taxonomy:"]
    for label, hint in zip(taxonomy.candidate_labels, taxonomy.nli_phrases):
        lines.append(f'- "{label}": {hint}')
    lines.extend(
        [
            f'- "{UNCLASSIFIED}": use this when no intent clearly matches',
            "",
            "Rules:",
            f'1) Output only taxonomy labels listed above. Never invent new labels. If uncertain, choose "{UNCLASSIFIED}".',
            '2) "confidence" must be a float in [0.0, 1.0].',
            '3) "reasoning" must be at most one sentence.',
            '4) "multi_intent" should contain labels only when multiple intents are clearly present; otherwise return [].',
        ]
    )
    return "\n".join(lines)


class LLMClassifier:
    """Single-model Ollama classifier initialized once at app startup."""

    def __init__(self, *, taxonomy: Taxonomy, base_url: str, model_name: str, timeout_seconds: float) -> None:
        self._taxonomy = taxonomy
        self._timeout_seconds = timeout_seconds
        self._model_name = model_name
        self._base_url = base_url
        self._system_instruction = _build_system_instruction(taxonomy)
        # Hash the full prompt string so wording changes automatically invalidate cache.
        self.system_instruction_hash = hashlib.sha256(self._system_instruction.encode("utf-8")).hexdigest()
        self._labels = set(taxonomy.candidate_labels) | {UNCLASSIFIED}
        self._client = httpx.AsyncClient(timeout=httpx.Timeout(timeout_seconds, connect=3.0))

    @property
    def model_name(self) -> str:
        return self._model_name

    async def close(self) -> None:
        await self._client.aclose()

    async def classify(self, text: str) -> dict[str, Any]:
        text_hash = _hash_text_prefix(text)
        response: httpx.Response | None = None
        schema_json = json.dumps(_RESPONSE_SCHEMA, separators=(",", ":"))
        user_prompt = (
            "Return ONLY valid JSON matching this schema exactly: "
            f"{schema_json}\n\n"
            f"Input text:\n{text}"
        )
        body = {
            "model": self._model_name,
            "stream": False,
            "messages": [
                {"role": "system", "content": self._system_instruction},
                {"role": "user", "content": user_prompt},
            ],
            "options": {"temperature": 0},
            "format": _RESPONSE_SCHEMA,
        }

        for attempt in range(2):
            try:
                response = await asyncio.wait_for(
                    self._client.post(self._base_url, json=body),
                    timeout=self._timeout_seconds,
                )
                response.raise_for_status()
                break
            except (asyncio.TimeoutError, httpx.HTTPError) as exc:
                if attempt == 0:
                    logger.warning("Ollama transient failure; retrying once: %s", exc)
                    await asyncio.sleep(1.0)
                else:
                    logger.error("Ollama failed after retry: %s", exc)
                    return dict(_FALLBACK_RESULT)
            except Exception as exc:  # pragma: no cover - defensive compatibility
                logger.error("Unexpected Ollama failure: %s", exc)
                return dict(_FALLBACK_RESULT)

        if response is None:
            return dict(_FALLBACK_RESULT)

        try:
            outer = response.json()
            raw_content = str(((outer.get("message") or {}).get("content")) or "")
            payload = json.loads(raw_content or "{}")
        except (ValueError, json.JSONDecodeError, TypeError) as exc:
            logger.warning("Ollama returned invalid JSON payload: %s", exc)
            return dict(_FALLBACK_RESULT)

        intent = str(payload.get("intent", UNCLASSIFIED))
        if intent not in self._labels:
            logger.warning("Gemini returned unknown label '%s'; forcing unclassified", intent)
            intent = UNCLASSIFIED

        try:
            confidence = float(payload.get("confidence", 0.0))
        except (TypeError, ValueError):
            confidence = 0.0
        confidence = max(0.0, min(1.0, confidence))

        reasoning = str(payload.get("reasoning", "")).strip() or "n/a"
        multi_intent_raw = payload.get("multi_intent", [])
        if isinstance(multi_intent_raw, list):
            multi_intent = [str(v) for v in multi_intent_raw if str(v) in self._labels and str(v) != intent]
        else:
            multi_intent = []

        logger.debug(
            "LLM classification text_hash=%s intent=%s confidence=%.3f reasoning=%s multi_intent=%s",
            text_hash,
            intent,
            confidence,
            reasoning,
            multi_intent,
        )
        return {
            "intent": intent,
            "confidence": confidence,
            "reasoning": reasoning,
            "multi_intent": multi_intent,
        }
