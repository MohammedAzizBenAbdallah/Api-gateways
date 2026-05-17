"""DistilBERT MNLI zero-shot intent classification (CPU)."""

from __future__ import annotations

import asyncio
import hashlib
import logging
from typing import Any

from app.taxonomy import UNCLASSIFIED, Taxonomy

logger = logging.getLogger(__name__)

_FALLBACK_RESULT: dict[str, Any] = {
    "intent": UNCLASSIFIED,
    "confidence": 0.0,
    "reasoning": "nli_error",
}


class NLIClassifier:
    """HuggingFace zero-shot pipeline; load once, infer via thread pool."""

    def __init__(
        self,
        *,
        taxonomy: Taxonomy,
        model_name: str,
        hypothesis_template: str | None = None,
        confidence_threshold: float,
    ) -> None:
        self._taxonomy = taxonomy
        self._model_name = model_name
        self._pipeline: Any = None
        self._hypothesis_template = hypothesis_template or taxonomy.hypothesis_template
        self._confidence_threshold = confidence_threshold
        # Map NLI phrase -> intent label (same order as taxonomy).
        self._phrase_to_label = dict(zip(taxonomy.nli_phrases, taxonomy.candidate_labels))
        self._candidate_phrases = list(taxonomy.nli_phrases)
        fingerprint_src = (
            f"{model_name}:{self._hypothesis_template}:"
            f"{','.join(taxonomy.candidate_labels)}"
        )
        self.fingerprint_hash = hashlib.sha256(fingerprint_src.encode("utf-8")).hexdigest()

    @property
    def model_name(self) -> str:
        return self._model_name

    def load(self) -> None:
        """Load model synchronously at startup (call before serving traffic)."""
        from transformers import pipeline

        logger.info("Loading zero-shot model %s (CPU)...", self._model_name)
        self._pipeline = pipeline(
            "zero-shot-classification",
            model=self._model_name,
            device=-1,
        )
        # Warm-up inference
        self._classify_sync("hello")
        logger.info("Zero-shot model ready")

    def _classify_sync(self, text: str) -> dict[str, Any]:
        if self._pipeline is None:
            return dict(_FALLBACK_RESULT)

        try:
            out = self._pipeline(
                text,
                self._candidate_phrases,
                hypothesis_template=self._hypothesis_template,
                multi_label=False,
            )
        except Exception as exc:
            logger.error("NLI inference failed: %s", exc)
            return dict(_FALLBACK_RESULT)

        labels = out.get("labels") or []
        scores = out.get("scores") or []
        if not labels or not scores:
            return dict(_FALLBACK_RESULT)

        top_phrase = str(labels[0])
        top_score = float(scores[0])
        intent = self._phrase_to_label.get(top_phrase, UNCLASSIFIED)
        if top_score < self._confidence_threshold:
            return {
                "intent": UNCLASSIFIED,
                "confidence": top_score,
                "reasoning": "below_threshold",
            }
        return {
            "intent": intent,
            "confidence": top_score,
            "reasoning": "nli",
        }

    async def classify(self, text: str) -> dict[str, Any]:
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self._classify_sync, text)
