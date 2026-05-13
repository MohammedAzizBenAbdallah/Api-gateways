# app/services/prompt_security_service.py
"""Prompt injection and jailbreak detection engine.

Scans incoming user messages against a curated pattern library and optional
DistilBERT injection classifier. Scores each prompt and blocks if the cumulative
score exceeds a threshold.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import re
from dataclasses import dataclass
from typing import Any, Callable, List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.text_utils import normalize_text
from app.models.security_pattern import SecurityPattern

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ScanResult:
    """Result of scanning a single prompt."""

    is_blocked: bool
    total_score: float
    matched_patterns: List[str]
    prompt_hash: str  # SHA-256 of the original prompt (never store plaintext)


@dataclass
class InjectionPattern:
    name: str
    pattern: re.Pattern[str]
    weight: float = 1.0
    description: str = ""


DEFAULT_BLOCK_THRESHOLD = 1.0
INJECTION_CONFIDENCE_THRESHOLD = 0.85
INJECTION_BLOCK_WEIGHT = 1.0

INJECTION_PATTERNS: List[InjectionPattern] = [
    InjectionPattern(
        name="ignore_previous_instructions",
        pattern=re.compile(
            r"ignore\s+(all\s+)?previous\s+(instructions|prompts|rules|context)",
            re.IGNORECASE,
        ),
        weight=1.0,
        description="Attempts to override system instructions",
    ),
    InjectionPattern(
        name="disregard_instructions",
        pattern=re.compile(
            r"disregard\s+(all\s+)?(previous|prior|above|earlier)\s+(instructions|prompts|rules)",
            re.IGNORECASE,
        ),
        weight=1.0,
        description="Variation of instruction override",
    ),
    InjectionPattern(
        name="forget_instructions",
        pattern=re.compile(
            r"forget\s+(everything|all|your)\s+(you\s+)?(were\s+)?(told|instructed|trained)",
            re.IGNORECASE,
        ),
        weight=1.0,
        description="Attempts to reset model context",
    ),
    InjectionPattern(
        name="dan_jailbreak",
        pattern=re.compile(
            r"\b(DAN|Do\s+Anything\s+Now)\b",
            re.IGNORECASE,
        ),
        weight=1.5,
        description="DAN (Do Anything Now) jailbreak attempt",
    ),
    InjectionPattern(
        name="developer_mode",
        pattern=re.compile(
            r"(developer|dev)\s+mode\s+(enabled|activated|on|override)",
            re.IGNORECASE,
        ),
        weight=1.2,
        description="Fake developer mode activation",
    ),
    InjectionPattern(
        name="jailbreak_keyword",
        pattern=re.compile(
            r"\b(jailbreak|jail\s*break|bypass\s+safety|bypass\s+filter)\b",
            re.IGNORECASE,
        ),
        weight=1.5,
        description="Explicit jailbreak keywords",
    ),
    InjectionPattern(
        name="roleplay_bypass",
        pattern=re.compile(
            r"(you\s+are\s+now|act\s+as|pretend\s+(to\s+be|you\s+are)|from\s+now\s+on\s+you\s+are)\s+(a\s+)?(an?\s+)?(evil|unrestricted|unfiltered|uncensored)",
            re.IGNORECASE,
        ),
        weight=1.0,
        description="Instructs model to adopt an unrestricted persona",
    ),
    InjectionPattern(
        name="hypothetical_bypass",
        pattern=re.compile(
            r"(hypothetically|in\s+a\s+fictional|for\s+educational\s+purposes|theoretically).{0,50}(how\s+to|steps\s+to|instructions\s+for).{0,50}(hack|exploit|attack|break\s+into|steal)",
            re.IGNORECASE,
        ),
        weight=0.8,
        description="Uses hypothetical framing to extract harmful content",
    ),
    InjectionPattern(
        name="system_prompt_leak",
        pattern=re.compile(
            r"(repeat|show|reveal|display|print|output)\s+(your\s+)?(system\s+prompt|initial\s+instructions|hidden\s+instructions|original\s+prompt)",
            re.IGNORECASE,
        ),
        weight=1.0,
        description="Attempts to extract the system prompt",
    ),
    InjectionPattern(
        name="what_are_your_instructions",
        pattern=re.compile(
            r"what\s+(are|were)\s+your\s+(original\s+|initial\s+|system\s+)?(instructions|rules|guidelines|prompt)",
            re.IGNORECASE,
        ),
        weight=0.6,
        description="Probing for system instructions",
    ),
    InjectionPattern(
        name="base64_injection",
        pattern=re.compile(
            r"(decode|interpret|execute|run)\s+(this\s+)?(base64|encoded|b64)",
            re.IGNORECASE,
        ),
        weight=0.7,
        description="Attempts to use encoding to bypass filters",
    ),
    InjectionPattern(
        name="markdown_injection",
        pattern=re.compile(
            r"!\[.*?\]\(https?://[^\s)]+\)",
            re.IGNORECASE,
        ),
        weight=0.5,
        description="Markdown image injection (potential exfiltration)",
    ),
    InjectionPattern(
        name="delimiter_injection",
        pattern=re.compile(
            r"(<\|im_start\|>|<\|im_end\|>|<\|system\|>|\[INST\]|\[/INST\]|<<SYS>>|<</SYS>>)",
            re.IGNORECASE,
        ),
        weight=1.5,
        description="Injects model-specific control tokens",
    ),
]


class InjectionClassifier:
    """DistilBERT-based prompt injection scoring (CPU; run via executor)."""

    MODEL_ID = "fmops/distilbert-prompt-injection"

    def __init__(self) -> None:
        self._pipeline: Any = None
        self._injection_label_matcher: Optional[Callable[[str], bool]] = None

    def load(self) -> None:
        """Load model and tokenizer into memory. Call from a worker thread at startup."""
        try:
            from transformers import pipeline  # type: ignore[import-untyped]

            pipe = pipeline(
                "text-classification",
                model=self.MODEL_ID,
                tokenizer=self.MODEL_ID,
                truncation=True,
                max_length=512,
            )
            self._pipeline = pipe
            id2label = getattr(pipe.model.config, "id2label", None) or {}
            inj_keywords = ("INJECT", "MALICIOUS", "ATTACK", "UNSAFE", "JAIL", "HACK")
            labels_inject: set[str] = set()
            for _k, v in id2label.items():
                vu = str(v).upper()
                if any(kw in vu for kw in inj_keywords):
                    labels_inject.add(str(v))

            if not labels_inject and len(id2label) == 2:
                # Binary classifier: assume label id 1 is the positive (injection) class.
                pos = id2label.get(1) or id2label.get("1")
                if pos is not None:
                    labels_inject.add(str(pos))

            def _match(label: str) -> bool:
                if label in labels_inject:
                    return True
                lu = label.upper()
                return any(kw in lu for kw in inj_keywords)

            self._injection_label_matcher = _match
            logger.info(
                "[InjectionClassifier] Loaded model=%s injection_labels=%s",
                self.MODEL_ID,
                sorted(labels_inject),
            )
        except Exception as exc:
            self._pipeline = None
            self._injection_label_matcher = None
            logger.warning(
                "[InjectionClassifier] Failed to load model %s: %s — regex-only mode",
                self.MODEL_ID,
                exc,
            )

    def score(self, text: str) -> float:
        """Return injection probability in [0, 1]."""
        if not self._pipeline or not text.strip():
            return 0.0
        matcher = self._injection_label_matcher
        if matcher is None:
            return 0.0
        try:
            rows = self._pipeline(
                text[:512],
                truncation=True,
                max_length=512,
                return_all_scores=True,
            )
            if not rows:
                return 0.0
            # pipeline may return nested list for batch size 1
            if isinstance(rows[0], list):
                rows = rows[0]
            inj = 0.0
            for item in rows:
                label = str(item.get("label", ""))
                sc = float(item.get("score", 0.0))
                if matcher(label):
                    inj = max(inj, sc)
            return inj
        except Exception as exc:
            logger.warning("[InjectionClassifier] Inference failed: %s", exc)
            return 0.0


class PromptSecurityService:
    """Scans prompts for injection attacks and jailbreak patterns."""

    def __init__(
        self,
        *,
        block_threshold: float = DEFAULT_BLOCK_THRESHOLD,
        injection_classifier: Optional[InjectionClassifier] = None,
    ) -> None:
        self._threshold = block_threshold
        self._patterns = list(INJECTION_PATTERNS)
        self._classifier = injection_classifier
        logger.info(
            "[PromptSecurity] Initialized with %d fallback patterns, threshold=%.1f distilbert=%s",
            len(self._patterns),
            self._threshold,
            injection_classifier is not None,
        )

    async def reload_patterns(self, session: AsyncSession) -> None:
        """Load active security patterns from the database and replace the active set."""
        result = await session.execute(
            select(SecurityPattern).where(SecurityPattern.is_active == True)
        )
        db_patterns = result.scalars().all()

        new_patterns = []
        for pat in db_patterns:
            try:
                compiled = re.compile(pat.pattern, re.IGNORECASE)
                new_patterns.append(
                    InjectionPattern(
                        name=pat.name,
                        pattern=compiled,
                        weight=float(pat.weight),
                        description=pat.description or "",
                    )
                )
            except re.error as exc:
                logger.error("[PromptSecurity] Failed to compile DB pattern '%s': %s", pat.name, exc)

        if new_patterns:
            self._patterns = new_patterns
            logger.info("[PromptSecurity] Reloaded %d active patterns from database.", len(self._patterns))
        else:
            logger.warning("[PromptSecurity] No active patterns found in DB, falling back to static list.")
            self._patterns = list(INJECTION_PATTERNS)

    def _run_regex(self, normalized: str) -> tuple[List[str], float]:
        matched: List[str] = []
        total_score = 0.0
        for pat in self._patterns:
            if pat.pattern.search(normalized):
                matched.append(pat.name)
                total_score += pat.weight
                logger.warning(
                    "[PromptSecurity] Pattern matched: %s (weight=%.1f)",
                    pat.name,
                    pat.weight,
                )
        return matched, total_score

    async def scan(self, prompt_text: str) -> ScanResult:
        """Scan a prompt and return a ScanResult (async for DistilBERT executor offload)."""
        prompt_hash = hashlib.sha256(prompt_text.encode("utf-8")).hexdigest()
        normalized = normalize_text(prompt_text)
        matched, total_score = self._run_regex(normalized)

        if self._classifier is not None:
            loop = asyncio.get_running_loop()
            injection_score = await loop.run_in_executor(
                None,
                self._classifier.score,
                normalized,
            )
            if injection_score >= INJECTION_CONFIDENCE_THRESHOLD:
                matched.append("distilbert_injection")
                total_score += INJECTION_BLOCK_WEIGHT
                logger.warning(
                    "[PromptSecurity] DistilBERT injection score=%.3f (threshold=%.3f)",
                    injection_score,
                    INJECTION_CONFIDENCE_THRESHOLD,
                )

        is_blocked = total_score >= self._threshold

        if is_blocked:
            logger.warning(
                "[PromptSecurity] BLOCKED — score=%.1f, threshold=%.1f, patterns=%s",
                total_score,
                self._threshold,
                matched,
            )

        return ScanResult(
            is_blocked=is_blocked,
            total_score=total_score,
            matched_patterns=matched,
            prompt_hash=prompt_hash,
        )

    async def scan_messages(self, messages: list[dict[str, str]]) -> ScanResult:
        """Scan only the latest user message from a conversation."""
        user_messages = [m for m in messages if m.get("role") == "user"]
        if not user_messages:
            return ScanResult(
                is_blocked=False,
                total_score=0.0,
                matched_patterns=[],
                prompt_hash=hashlib.sha256(b"").hexdigest(),
            )
        latest = user_messages[-1].get("content", "") or ""
        return await self.scan(latest)
