# app/services/output_guard_service.py
"""AI output validation and PII redaction engine.

Scans AI-generated responses for PII (emails, phones, SSNs, credit cards)
and replaces them with [REDACTED:TYPE] placeholders before delivery to the client.

Supports two modes:
- Full text redaction (for JSON responses or buffered streams)
- Windowed chunk redaction (for SSE streaming with a carry-over buffer)
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import List, Optional, Tuple

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RedactionResult:
    """Result of redacting a text block."""
    redacted_text: str
    redaction_count: int
    redacted_types: List[str]


# ── PII Patterns for Output Scanning ────────────────────────────────────────
# These are intentionally tuned for AI output (which tends to generate
# well-formatted PII rather than the noisy patterns found in user input).

_EMAIL_PATTERN = re.compile(r"[\w.\-+]+@[\w.\-]+\.\w{2,}")
_PHONE_US_PATTERN = re.compile(
    r"(?<!\w)(?:\+?1[-.\s]?)?(?:\(\d{3}\)|\d{3})[-.\s]?\d{3}[-.\s]?\d{4}(?!\w)"
)
_PHONE_INTL_PATTERN = re.compile(r"(?<!\w)\+[1-9]\d{6,14}(?!\w)")
_SSN_PATTERN = re.compile(r"(?<!\w)\d{3}-\d{2}-\d{4}(?!\w)")
_CC_PATTERN = re.compile(r"(?<!\w)(?:\d[ -]*?){13,19}(?!\w)")
_IBAN_PATTERN = re.compile(r"(?<!\w)[A-Z]{2}\d{2}[A-Z0-9]{11,30}(?!\w)", re.I)

# Address patterns
_PO_BOX_PATTERN = re.compile(r"(?<!\w)P\.?\s*O\.?\s*Box\s*\d{1,6}(?!\w)", re.I)
_STREET_PATTERN = re.compile(
    r"(?<!\w)\d{1,6}\s+"
    r"(?:[A-Za-z0-9.\-]+\s+){0,4}"
    r"(?:Street|St\.?|Avenue|Ave\.?|Road|Rd\.?|Boulevard|Blvd\.?|Lane|Ln\.?|"
    r"Drive|Dr\.?|Court|Ct\.?|Way|Terrace|Ter\.?|Circle|Cir\.?|Place|Pl\.?)"
    r"(?!\w)",
    re.I,
)

# Name patterns (common AI output format: "Mr./Mrs./Dr. FirstName LastName")
_FORMAL_NAME_PATTERN = re.compile(
    r"(?<!\w)(?:Mr\.|Mrs\.|Ms\.|Dr\.|Prof\.)\s+[A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,2}(?!\w)"
)


def _luhn_check(number_digits: str) -> bool:
    """Validate credit card candidate using Luhn algorithm."""
    digits = [int(d) for d in number_digits]
    checksum = 0
    for i, d in enumerate(reversed(digits)):
        if i % 2 == 1:
            d *= 2
            if d > 9:
                d -= 9
        checksum += d
    return checksum % 10 == 0


# Ordered list of (pattern, type_label, validator_fn).
# Validators return True if the match is a real PII entity.
_OUTPUT_PII_RULES: List[Tuple[re.Pattern, str, Optional[callable]]] = [
    (_SSN_PATTERN, "SSN", None),
    (_EMAIL_PATTERN, "EMAIL", None),
    (_PHONE_US_PATTERN, "PHONE", None),
    (_PHONE_INTL_PATTERN, "PHONE", None),
    (_PO_BOX_PATTERN, "ADDRESS", None),
    (_STREET_PATTERN, "ADDRESS", None),
    (_FORMAL_NAME_PATTERN, "NAME", None),
    (_IBAN_PATTERN, "IBAN", None),
    # Credit cards need Luhn validation to reduce false positives.
    (_CC_PATTERN, "CREDIT_CARD", lambda m: _luhn_check(re.sub(r"\D", "", m.group(0)))),
]


class OutputGuardService:
    """Scans and redacts PII from AI-generated output text."""

    def __init__(self) -> None:
        logger.info(
            "[OutputGuard] Initialized with %d PII detection rules",
            len(_OUTPUT_PII_RULES),
        )

    def redact(self, text: str) -> RedactionResult:
        """Scan text and replace all detected PII with [REDACTED:TYPE] placeholders.

        Returns a RedactionResult with the sanitized text and metadata.
        """
        redacted_types: List[str] = []
        redaction_count = 0
        result_text = text

        for pattern, type_label, validator_fn in _OUTPUT_PII_RULES:
            matches = list(pattern.finditer(result_text))
            for match in reversed(matches):  # Reverse to preserve indices
                if validator_fn and not validator_fn(match):
                    continue
                placeholder = f"[REDACTED:{type_label}]"
                result_text = (
                    result_text[: match.start()]
                    + placeholder
                    + result_text[match.end() :]
                )
                redaction_count += 1
                if type_label not in redacted_types:
                    redacted_types.append(type_label)

        if redaction_count > 0:
            logger.info(
                "[OutputGuard] Redacted %d PII entities: %s",
                redaction_count,
                redacted_types,
            )

        return RedactionResult(
            redacted_text=result_text,
            redaction_count=redaction_count,
            redacted_types=sorted(redacted_types),
        )

    def redact_stream_chunk(
        self, chunk: str, carry_buffer: str = ""
    ) -> Tuple[str, str]:
        """Redact PII from a streaming chunk with a carry-over buffer.

        Because PII (like a phone number) might be split across two SSE chunks,
        we prepend the previous chunk's tail (carry_buffer) to the current chunk
        for scanning. After redaction, we hold back the last N characters as the
        new carry_buffer for the next chunk.

        Returns:
            (safe_text_to_send, new_carry_buffer)
        """
        CARRY_SIZE = 30  # Enough to capture most PII tokens split at boundary

        combined = carry_buffer + chunk

        # Redact the combined text
        result = self.redact(combined)
        redacted = result.redacted_text

        # Hold back the tail as carry buffer for next chunk
        if len(redacted) > CARRY_SIZE:
            safe_to_send = redacted[:-CARRY_SIZE]
            new_carry = redacted[-CARRY_SIZE:]
        else:
            # Chunk too small to split; hold everything
            safe_to_send = ""
            new_carry = redacted

        return safe_to_send, new_carry
