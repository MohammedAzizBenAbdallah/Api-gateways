# app/services/prompt_security_service.py
"""Prompt injection and jailbreak detection engine.

Scans incoming user messages against a curated pattern library.
Scores each prompt and blocks if the cumulative score exceeds a threshold.
"""

from __future__ import annotations

import hashlib
import logging
import re
from dataclasses import dataclass, field
from typing import List, Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.security_pattern import SecurityPattern

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ScanResult:
    """Result of scanning a single prompt."""
    is_blocked: bool
    total_score: float
    matched_patterns: List[str]
    prompt_hash: str  # SHA-256 of the original prompt (never store plaintext)


# ── Pattern Library ──────────────────────────────────────────────────────────
# Each pattern has a name, compiled regex, and a weight (score contribution).
# Scoring allows nuanced decisions: a single weak match won't block,
# but multiple weak matches or one strong match will.

@dataclass
class InjectionPattern:
    name: str
    pattern: re.Pattern[str]
    weight: float = 1.0
    description: str = ""


# Default threshold: if cumulative score >= this value, the prompt is blocked.
DEFAULT_BLOCK_THRESHOLD = 1.0

INJECTION_PATTERNS: List[InjectionPattern] = [
    # ── Direct Instruction Override ──
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

    # ── Jailbreak Personas ──
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

    # ── Role-Play Bypass ──
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

    # ── System Prompt Extraction ──
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

    # ── Encoding/Obfuscation Attacks ──
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

    # ── Token Smuggling ──
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


class PromptSecurityService:
    """Scans prompts for injection attacks and jailbreak patterns."""

    def __init__(self, *, block_threshold: float = DEFAULT_BLOCK_THRESHOLD) -> None:
        self._threshold = block_threshold
        self._patterns = list(INJECTION_PATTERNS)
        logger.info(
            "[PromptSecurity] Initialized with %d fallback patterns, threshold=%.1f",
            len(self._patterns),
            self._threshold,
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
                        description=pat.description or ""
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

    def scan(self, prompt_text: str) -> ScanResult:
        """Scan a prompt and return a ScanResult.

        The prompt is hashed (SHA-256) for audit logging.
        The plaintext is NEVER persisted.
        """
        prompt_hash = hashlib.sha256(prompt_text.encode("utf-8")).hexdigest()
        matched: List[str] = []
        total_score = 0.0

        for pat in self._patterns:
            if pat.pattern.search(prompt_text):
                matched.append(pat.name)
                total_score += pat.weight
                logger.warning(
                    "[PromptSecurity] Pattern matched: %s (weight=%.1f)",
                    pat.name,
                    pat.weight,
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

    def scan_messages(self, messages: list[dict[str, str]]) -> ScanResult:
        """Scan only the latest user message from a conversation."""
        # We only scan the latest message to avoid re-flagging history.
        user_messages = [m for m in messages if m.get("role") == "user"]
        if not user_messages:
            return ScanResult(
                is_blocked=False,
                total_score=0.0,
                matched_patterns=[],
                prompt_hash=hashlib.sha256(b"").hexdigest(),
            )
        latest = user_messages[-1].get("content", "")
        return self.scan(latest)
