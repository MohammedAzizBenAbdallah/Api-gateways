# app/core/text_utils.py
"""Shared text normalization for security and content inspection."""

from __future__ import annotations

import re
import unicodedata


# Categories to strip (zero-width, format characters, etc.)
_DISALLOWED_CATEGORIES = frozenset({"Cf", "Mn", "Me"})


def normalize_text(text: str) -> str:
    """Normalize user text before scanners.

    - NFKC: compatibility decomposition + canonical composition (homoglyphs)
    - Remove invisible / zero-width / combining marks used for obfuscation
    - Collapse whitespace
    """
    if not text:
        return ""
    normalized = unicodedata.normalize("NFKC", text)
    chars: list[str] = []
    for ch in normalized:
        cat = unicodedata.category(ch)
        if cat in _DISALLOWED_CATEGORIES:
            continue
        # Strip common zero-width / BOM code points even if miscategorized
        if ord(ch) in (0xFEFF, 0x200B, 0x200C, 0x200D, 0x2060, 0x2061, 0x2062, 0x2063):
            continue
        chars.append(ch)
    collapsed = "".join(chars)
    collapsed = re.sub(r"\s+", " ", collapsed, flags=re.UNICODE).strip()
    return collapsed
