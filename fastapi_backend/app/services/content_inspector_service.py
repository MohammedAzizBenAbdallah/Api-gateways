# app/services/content_inspector_service.py
"""Resolve request sensitivity by detecting potential PII.

Classification-only: LOW/MEDIUM -> HIGH when potential PII is detected.

PII redaction-by-logging: we log only *types and counts* of detected PII,
never the matched raw substrings.
"""

from __future__ import annotations

import os
import logging
import re
from typing import Any, Dict, List, Set

from app.schemas.ai_request import AIRequestSchema, SensitivityLevel

logger = logging.getLogger(__name__)

# spaCy entity labels treated as PII.
# Defaults are intentionally high-signal; low-signal types are opt-in (prod-only, per intent).
SPACY_HIGH_SIGNAL_TYPES: frozenset[str] = frozenset({"PERSON", "PHONE"})
SPACY_LOW_SIGNAL_TYPES: frozenset[str] = frozenset({"ORG", "GPE", "LOC"})

# Regex for email addresses (spaCy en_core_web_sm misses many emails).
EMAIL_PATTERN: re.Pattern[str] = re.compile(r"[\w\.\-]+@[\w\.\-]+\.\w+")

# Phone patterns (intentionally conservative).
PHONE_PATTERN_US: re.Pattern[str] = re.compile(
    r"(?<!\w)(?:\+?1[-.\s]?)?(?:\(\d{3}\)|\d{3})[-.\s]?\d{3}[-.\s]?\d{4}(?!\w)"
)
PHONE_PATTERN_E164: re.Pattern[str] = re.compile(r"(?<!\w)\+[1-9]\d{6,14}(?!\w)")

# SSN: standard US format.
SSN_PATTERN: re.Pattern[str] = re.compile(r"(?<!\w)\d{3}-\d{2}-\d{4}(?!\w)")

# Credit cards: find candidates then validate using Luhn.
CC_CANDIDATE_PATTERN: re.Pattern[str] = re.compile(r"(?<!\w)(?:\d[ -]*?){13,19}(?!\w)")

# IBAN: basic structure check (2 letters + 2 digits + up to 30 alnum).
IBAN_PATTERN: re.Pattern[str] = re.compile(r"(?<!\w)[A-Z]{2}\d{2}[A-Z0-9]{11,30}(?!\w)", re.I)

# Address heuristics: "123 Main St" / PO Box.
PO_BOX_PATTERN: re.Pattern[str] = re.compile(r"(?<!\w)P\.?\s*O\.?\s*Box\s*\d{1,6}(?!\w)", re.I)
STREET_ADDRESS_PATTERN: re.Pattern[str] = re.compile(
    r"(?<!\w)\d{1,6}\s+"
    r"(?:[A-Za-z0-9.\-]+\s+){0,4}"
    r"(?:Street|St\.?|Avenue|Ave\.?|Road|Rd\.?|Boulevard|Blvd\.?|Lane|Ln\.?|Drive|Dr\.?|Court|Ct\.?|"
    r"Way|Terrace|Ter\.?|Circle|Cir\.?|Place|Pl\.?)"
    r"(?!\w)",
    re.I,
)

# JWTs: base64url-like segments; jwt header often starts with "eyJ".
JWT_PATTERN: re.Pattern[str] = re.compile(
    r"(?<!\w)eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}(?!\w)"
)

# API keys (a few common high-signal patterns).
API_KEY_AWS_ACCESS_PATTERN: re.Pattern[str] = re.compile(r"(?<!\w)AKIA[0-9A-Z]{16}(?!\w)")
API_KEY_GOOGLE_PATTERN: re.Pattern[str] = re.compile(r"(?<!\w)AIza[0-9A-Za-z\-_]{35}(?!\w)")
API_KEY_GITHUB_PATTERN: re.Pattern[str] = re.compile(r"(?<!\w)ghp_[A-Za-z0-9]{36}(?!\w)")
API_KEY_GENERIC_ASSIGNMENT_PATTERN: re.Pattern[str] = re.compile(
    r"(?<!\w)(?:api[_-]?key|apikey|secret|token)\s*[:=]\s*[A-Za-z0-9\-_]{16,}(?!\w)",
    re.I,
)


def _luhn_check(number_digits: str) -> bool:
    """Validate a credit card number candidate using the Luhn algorithm."""
    digits = [int(d) for d in number_digits]
    checksum = 0
    # Standard Luhn: starting from the rightmost digit, double every second digit.
    for i, d in enumerate(reversed(digits)):
        if i % 2 == 1:
            d *= 2
            if d > 9:
                d -= 9
        checksum += d
    return checksum % 10 == 0


def _iban_mod97_check(iban_alnum: str) -> bool:
    """Basic mod-97 check for IBANs to reduce false positives."""
    iban = iban_alnum.replace(" ", "").upper()
    if len(iban) < 15 or len(iban) > 34:
        return False
    rearranged = iban[4:] + iban[:4]

    # Convert letters to numbers: A=10 .. Z=35
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
    # Iterate in chunks to avoid big ints.
    for chunk_i in range(0, len(converted_str), 9):
        remainder = int(str(remainder) + converted_str[chunk_i : chunk_i + 9]) % 97
    return remainder == 1


def _parse_allowed_low_signal_intents() -> Set[str]:
    """Read intent list from env (prod-only)."""
    raw = os.getenv("PII_ALLOW_LOW_SIGNAL_INTENTS", "").strip()
    if not raw:
        return set()
    return {part.strip() for part in raw.split(",") if part.strip()}


def _resolve_spacy_labels_for_upgrade(*, intent: str, environment: str) -> frozenset[str]:
    """Return spaCy entity labels that should be treated as PII for this request."""
    labels: Set[str] = set(SPACY_HIGH_SIGNAL_TYPES)
    # Default excludes ORG/GPE/LOC; enable in prod per intent via env var.
    if environment == "prod" and intent in _parse_allowed_low_signal_intents():
        labels |= set(SPACY_LOW_SIGNAL_TYPES)
    return frozenset(labels)


def _count_regex_matches(pattern: re.Pattern[str], text: str) -> int:
    return sum(1 for _ in pattern.finditer(text))


class ContentInspectorService:
    """Business logic for content inspection and sensitivity upgrades."""

    async def inspect_content(
        self, body: AIRequestSchema, nlp: Any
    ) -> tuple[SensitivityLevel, List[str], int]:
        """Inspect message content and return (resolved_sensitivity, detected_pii_types, total_count).

        Notes:
        - If declared sensitivity is already HIGH, this returns (HIGH, []) and does not call nlp.
        - `detected_pii_types` is a deduped, sorted list of detector type strings.
        """
        declared: SensitivityLevel = SensitivityLevel(body.metadata.sensitivity)
        if declared is SensitivityLevel.HIGH:
            return SensitivityLevel.HIGH, [], 0

        messages = getattr(body.payload, "messages", [])
        # BEFORE: we scanned the entire conversation history, which caused "PII bleed"
        # (old PII in earlier turns upgrading new clean turns to HIGH).
        #
        # AFTER: scan only the most recent message. Prior turns are already persisted with
        # their own resolved sensitivity, and re-scanning them on every request is incorrect.
        if not messages:
            return declared, [], 0
        last = messages[-1]
        combined_text = getattr(last, "content", "") or ""
        if not combined_text.strip():
            return declared, [], 0

        detected_counts: Dict[str, int] = {}

        def _add_detected(type_name: str, count: int = 1) -> None:
            if count <= 0:
                return
            detected_counts[type_name] = detected_counts.get(type_name, 0) + count

        # Deterministic detectors (model-independent).
        _add_detected("EMAIL", _count_regex_matches(EMAIL_PATTERN, combined_text))
        _add_detected("PHONE", _count_regex_matches(PHONE_PATTERN_US, combined_text))
        _add_detected("PHONE", _count_regex_matches(PHONE_PATTERN_E164, combined_text))
        _add_detected("SSN", _count_regex_matches(SSN_PATTERN, combined_text))

        # Credit cards: Luhn validation.
        cc_candidates = [m.group(0) for m in CC_CANDIDATE_PATTERN.finditer(combined_text)]
        cc_valid = 0
        for cand in cc_candidates:
            digits_only = re.sub(r"\D", "", cand)
            if 13 <= len(digits_only) <= 19 and _luhn_check(digits_only):
                cc_valid += 1
        _add_detected("CREDIT_CARD", cc_valid)

        # IBAN: basic match + mod-97 check.
        iban_candidates = [m.group(0).replace(" ", "") for m in IBAN_PATTERN.finditer(combined_text)]
        iban_valid = 0
        for iban in iban_candidates:
            if _iban_mod97_check(iban):
                iban_valid += 1
        _add_detected("IBAN", iban_valid)

        # Address heuristics.
        _add_detected("ADDRESS", _count_regex_matches(PO_BOX_PATTERN, combined_text))
        _add_detected("ADDRESS", _count_regex_matches(STREET_ADDRESS_PATTERN, combined_text))

        # Secrets / credentials.
        _add_detected("JWT", _count_regex_matches(JWT_PATTERN, combined_text))
        _add_detected("API_KEY", _count_regex_matches(API_KEY_AWS_ACCESS_PATTERN, combined_text))
        _add_detected("API_KEY", _count_regex_matches(API_KEY_GOOGLE_PATTERN, combined_text))
        _add_detected("API_KEY", _count_regex_matches(API_KEY_GITHUB_PATTERN, combined_text))
        _add_detected("API_KEY", _count_regex_matches(API_KEY_GENERIC_ASSIGNMENT_PATTERN, combined_text))

        # Optional spaCy NER for entity categories (configurable).
        doc = nlp(combined_text)
        allowed_spacy_labels = _resolve_spacy_labels_for_upgrade(
            intent=body.intent,
            environment=body.metadata.environment,
        )
        for ent in doc.ents:
            if ent.label_ in allowed_spacy_labels:
                _add_detected(ent.label_, 1)

        if detected_counts:
            detected_types = sorted(detected_counts.keys())
            total_count = sum(detected_counts.values())
            logger.info(
                "[ContentInspector] PII detected %s",
                {"types": detected_types, "count": total_count},
            )
            logger.info(
                "[ContentInspector] Upgrading sensitivity %s → HIGH due to PII.",
                declared.value,
            )
            return SensitivityLevel.HIGH, detected_types, total_count

        logger.debug(
            "[ContentInspector] No PII detected — sensitivity remains %s",
            declared.value,
        )
        return declared, [], 0

    async def resolve_sensitivity(self, body: AIRequestSchema, nlp: Any) -> SensitivityLevel:
        """Return the final resolved SensitivityLevel."""
        resolved, _types, _count = await self.inspect_content(body, nlp)
        return resolved

