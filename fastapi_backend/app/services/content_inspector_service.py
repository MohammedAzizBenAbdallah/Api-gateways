# app/services/content_inspector_service.py
"""Resolve request sensitivity by detecting potential PII.

Classification-only: LOW/MEDIUM -> HIGH when potential PII is detected.

PII redaction-by-logging: we log only *types and counts* of detected PII,
never the matched raw substrings.
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
from typing import Any, Dict, List, Set

from presidio_analyzer import AnalyzerEngine
from presidio_analyzer.nlp_engine import NlpEngineProvider

from app.core.text_utils import normalize_text
from app.schemas.ai_request import AIRequestSchema, SensitivityLevel

logger = logging.getLogger(__name__)

# PII Sensitivity Tiers mapping entity types to SensitivityLevel.
# None means the entity is tolerated (no automatic upgrade).
PII_SENSITIVITY_TIERS: Dict[str, SensitivityLevel | None] = {
    # Always HIGH — critical secrets / financial / identity
    "SSN": SensitivityLevel.HIGH,
    "CREDIT_CARD": SensitivityLevel.HIGH,
    "IBAN": SensitivityLevel.HIGH,
    "JWT": SensitivityLevel.HIGH,
    "API_KEY": SensitivityLevel.HIGH,
    "US_PASSPORT": SensitivityLevel.HIGH,
    "MEDICAL_LICENSE": SensitivityLevel.HIGH,
    # MEDIUM — personal but not catastrophic alone
    "EMAIL": SensitivityLevel.MEDIUM,
    "PHONE": SensitivityLevel.MEDIUM,
    "ADDRESS": SensitivityLevel.MEDIUM,
    "PERSON": SensitivityLevel.MEDIUM,
    # LOW signal — don't upgrade at all (tolerated)
    "DATE_TIME": None,
    "ORGANIZATION": None,
    "LOCATION": None,
    "URL": None,
}

EMAIL_PATTERN: re.Pattern[str] = re.compile(r"[\w\.\-]+@[\w\.\-]+\.\w+")

PHONE_PATTERN_US: re.Pattern[str] = re.compile(
    r"(?<!\w)(?:\+?1[-.\s]?)?(?:\(\d{3}\)|\d{3})[-.\s]?\d{3}[-.\s]?\d{4}(?!\w)"
)
PHONE_PATTERN_E164: re.Pattern[str] = re.compile(r"(?<!\w)\+[1-9]\d{6,14}(?!\w)")

SSN_PATTERN: re.Pattern[str] = re.compile(r"(?<!\w)\d{3}-\d{2}-\d{4}(?!\w)")

CC_CANDIDATE_PATTERN: re.Pattern[str] = re.compile(r"(?<!\w)(?:\d[ -]*?){13,19}(?!\w)")

IBAN_PATTERN: re.Pattern[str] = re.compile(r"(?<!\w)[A-Z]{2}\d{2}[A-Z0-9]{11,30}(?!\w)", re.I)

PO_BOX_PATTERN: re.Pattern[str] = re.compile(r"(?<!\w)P\.?\s*O\.?\s*Box\s*\d{1,6}(?!\w)", re.I)
STREET_ADDRESS_PATTERN: re.Pattern[str] = re.compile(
    r"(?<!\w)\d{1,6}\s+"
    r"(?:[A-Za-z0-9.\-]+\s+){0,4}"
    r"(?:Street|St\.?|Avenue|Ave\.?|Road|Rd\.?|Boulevard|Blvd\.?|Lane|Ln\.?|Drive|Dr\.?|Court|Ct\.?|"
    r"Way|Terrace|Ter\.?|Circle|Cir\.?|Place|Pl\.?)"
    r"(?!\w)",
    re.I,
)

US_PASSPORT_PATTERN: re.Pattern[str] = re.compile(r"(?<!\w)[A-Z0-9]{9}(?!\w)")
MEDICAL_LICENSE_PATTERN: re.Pattern[str] = re.compile(r"(?<!\w)[A-Z]{2}\d{7}(?!\w)")
STREET_ADDRESS_PATTERN: re.Pattern[str] = re.compile(
    r"(?<!\w)\d{1,6}\s+"
    r"(?:[A-Za-z0-9.\-]+\s+){0,4}"
    r"(?:Street|St\.?|Avenue|Ave\.?|Road|Rd\.?|Boulevard|Blvd\.?|Lane|Ln\.?|Drive|Dr\.?|Court|Ct\.?|"
    r"Way|Terrace|Ter\.?|Circle|Cir\.?|Place|Pl\.?)"
    r"(?!\w)",
    re.I,
)

JWT_PATTERN: re.Pattern[str] = re.compile(
    r"(?<!\w)eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}(?!\w)"
)

API_KEY_AWS_ACCESS_PATTERN: re.Pattern[str] = re.compile(r"(?<!\w)AKIA[0-9A-Z]{16}(?!\w)")
API_KEY_GOOGLE_PATTERN: re.Pattern[str] = re.compile(r"(?<!\w)AIza[0-9A-Za-z\-_]{35}(?!\w)")
API_KEY_GITHUB_PATTERN: re.Pattern[str] = re.compile(r"(?<!\w)ghp_[A-Za-z0-9]{36}(?!\w)")
API_KEY_GENERIC_ASSIGNMENT_PATTERN: re.Pattern[str] = re.compile(
    r"(?<!\w)(?:api[_-]?key|apikey|secret|token)\s*[:=]\s*[A-Za-z0-9\-_]{16,}(?!\w)",
    re.I,
)

# Use the same spaCy model baked into the Docker image (see Dockerfile).
# Presidio's default is en_core_web_lg (~400 MB) which it downloads on first use.
PRESIDIO_SPACY_MODEL = os.getenv("PRESIDIO_SPACY_MODEL", "en_core_web_sm")

_analyzer_engine: AnalyzerEngine | None = None


def _create_presidio_analyzer() -> AnalyzerEngine:
    """Build Presidio with an explicit spaCy model — avoids runtime downloads."""
    configuration = {
        "nlp_engine_name": "spacy",
        "models": [{"lang_code": "en", "model_name": PRESIDIO_SPACY_MODEL}],
    }
    provider = NlpEngineProvider(nlp_configuration=configuration)
    return AnalyzerEngine(nlp_engine=provider.create_engine())


def _get_presidio_analyzer() -> AnalyzerEngine:
    global _analyzer_engine
    if _analyzer_engine is None:
        _analyzer_engine = _create_presidio_analyzer()
    return _analyzer_engine


def warmup_presidio_analyzer() -> None:
    """Eager-load Presidio + spaCy at startup (CPU-bound; run in executor)."""
    analyzer = _get_presidio_analyzer()
    analyzer.analyze(text="startup warmup", language="en")
    logger.info(
        "[ContentInspector] Presidio analyzer warm-up complete (model=%s)",
        PRESIDIO_SPACY_MODEL,
    )


def _luhn_check(number_digits: str) -> bool:
    digits = [int(d) for d in number_digits]
    checksum = 0
    for i, d in enumerate(reversed(digits)):
        if i % 2 == 1:
            d *= 2
            if d > 9:
                d -= 9
        checksum += d
    return checksum % 10 == 0


def _iban_mod97_check(iban_alnum: str) -> bool:
    iban = iban_alnum.replace(" ", "").upper()
    if len(iban) < 15 or len(iban) > 34:
        return False
    rearranged = iban[4:] + iban[:4]

    converted_parts: List[str] = []
    for ch in rearranged:
        if ch.isdigit():
            converted_parts.append(ch)
        elif "A" <= ch <= "Z":
            converted_parts.append(str(ord(ch) - ord("A") + 10))
        else:
            return False

    converted_str = "".join(converted_parts)

    remainder = 0
    for chunk_i in range(0, len(converted_str), 9):
        remainder = int(str(remainder) + converted_str[chunk_i : chunk_i + 9]) % 97
    return remainder == 1


def _parse_allowed_low_signal_intents() -> Set[str]:
    raw = os.getenv("PII_ALLOW_LOW_SIGNAL_INTENTS", "").strip()
    if not raw:
        return set()
    return {part.strip() for part in raw.split(",") if part.strip()}


def _get_target_sensitivity(entity_type: str) -> SensitivityLevel | None:
    """Return the sensitivity level this entity type should trigger."""
    return PII_SENSITIVITY_TIERS.get(entity_type)


def _count_regex_matches(pattern: re.Pattern[str], text: str) -> int:
    return sum(1 for _ in pattern.finditer(text))


class ContentInspectorService:
    """Business logic for content inspection and sensitivity upgrades."""

    async def inspect_content(
        self, body: AIRequestSchema, nlp: Any
    ) -> tuple[SensitivityLevel, List[str], int]:
        """Inspect message content and return (resolved_sensitivity, detected_pii_types, total_count).

        `nlp` is retained for API compatibility; inspection uses Presidio + regex.
        """
        _ = nlp  # unused — Presidio provides NER-style PII detection

        declared: SensitivityLevel = SensitivityLevel(body.metadata.sensitivity)
        if declared is SensitivityLevel.HIGH:
            return SensitivityLevel.HIGH, [], 0

        messages = getattr(body.payload, "messages", [])
        if not messages:
            return declared, [], 0
        last = messages[-1]
        combined_text = getattr(last, "content", "") or ""
        if not combined_text.strip():
            return declared, [], 0

        combined_text = normalize_text(combined_text)

        detected_counts: Dict[str, int] = {}

        def _add_detected(type_name: str, count: int = 1) -> None:
            if count <= 0:
                return
            detected_counts[type_name] = detected_counts.get(type_name, 0) + count

        _add_detected("EMAIL", _count_regex_matches(EMAIL_PATTERN, combined_text))
        _add_detected("PHONE", _count_regex_matches(PHONE_PATTERN_US, combined_text))
        _add_detected("PHONE", _count_regex_matches(PHONE_PATTERN_E164, combined_text))
        _add_detected("SSN", _count_regex_matches(SSN_PATTERN, combined_text))

        cc_candidates = [m.group(0) for m in CC_CANDIDATE_PATTERN.finditer(combined_text)]
        cc_valid = 0
        for cand in cc_candidates:
            digits_only = re.sub(r"\D", "", cand)
            if 13 <= len(digits_only) <= 19 and _luhn_check(digits_only):
                cc_valid += 1
        _add_detected("CREDIT_CARD", cc_valid)

        iban_candidates = [m.group(0).replace(" ", "") for m in IBAN_PATTERN.finditer(combined_text)]
        iban_valid = 0
        for iban in iban_candidates:
            if _iban_mod97_check(iban):
                iban_valid += 1
        _add_detected("IBAN", iban_valid)

        _add_detected("ADDRESS", _count_regex_matches(PO_BOX_PATTERN, combined_text))
        _add_detected("ADDRESS", _count_regex_matches(STREET_ADDRESS_PATTERN, combined_text))

        _add_detected("JWT", _count_regex_matches(JWT_PATTERN, combined_text))
        _add_detected("API_KEY", _count_regex_matches(API_KEY_AWS_ACCESS_PATTERN, combined_text))
        _add_detected("API_KEY", _count_regex_matches(API_KEY_GOOGLE_PATTERN, combined_text))
        _add_detected("API_KEY", _count_regex_matches(API_KEY_GITHUB_PATTERN, combined_text))
        _add_detected("API_KEY", _count_regex_matches(API_KEY_GENERIC_ASSIGNMENT_PATTERN, combined_text))

        _add_detected("US_PASSPORT", _count_regex_matches(US_PASSPORT_PATTERN, combined_text))
        _add_detected("MEDICAL_LICENSE", _count_regex_matches(MEDICAL_LICENSE_PATTERN, combined_text))

        try:
            analyzer = _get_presidio_analyzer()
            loop = asyncio.get_running_loop()
            results = await loop.run_in_executor(
                None, analyzer.analyze, combined_text, "en"
            )
            for r in results:
                et = str(r.entity_type)
                _add_detected(et, 1)
        except Exception as exc:
            logger.warning("[ContentInspector] Presidio analyze failed: %s", exc)

        # Resolve the highest sensitivity level among all detected PII types
        highest_tier: SensitivityLevel = declared
        for et in detected_counts.keys():
            tier = _get_target_sensitivity(et)
            if tier is None:
                continue
            
            # Compare and upgrade if the new tier is higher
            if tier == SensitivityLevel.HIGH:
                highest_tier = SensitivityLevel.HIGH
                break  # Can't go higher than HIGH
            elif tier == SensitivityLevel.MEDIUM and highest_tier != SensitivityLevel.HIGH:
                highest_tier = SensitivityLevel.MEDIUM

        if highest_tier != declared:
            detected_types = sorted(detected_counts.keys())
            total_count = sum(detected_counts.values())
            logger.info(
                "[ContentInspector] PII detected %s. Upgrading sensitivity %s → %s",
                {"types": detected_types, "count": total_count},
                declared.value,
                highest_tier.value,
            )
            return highest_tier, detected_types, total_count

        logger.debug(
            "[ContentInspector] PII detected but none triggered a sensitivity upgrade — remains %s",
            declared.value,
        )
        return declared, sorted(detected_counts.keys()), sum(detected_counts.values())

    async def resolve_sensitivity(self, body: AIRequestSchema, nlp: Any) -> SensitivityLevel:
        """Return the final resolved SensitivityLevel."""
        resolved, _types, _count = await self.inspect_content(body, nlp)
        return resolved
