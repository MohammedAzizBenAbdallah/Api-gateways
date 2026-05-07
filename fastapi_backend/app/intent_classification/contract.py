"""Load canonical intent taxonomy and validation helpers."""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, FrozenSet, List

import yaml

UNCLASSIFIED_LABEL = "unclassified"


@dataclass(frozen=True)
class IntentTaxonomyV1:
    """Versioned taxonomy for routing + classification."""

    version: str
    confidence_threshold: float
    candidate_labels: tuple[str, ...]

    @property
    def routable_labels(self) -> FrozenSet[str]:
        """Intents that may be assigned after classification (includes unclassified)."""
        return frozenset(self.candidate_labels) | {UNCLASSIFIED_LABEL}


def _default_taxonomy_path() -> Path:
    """Resolve taxonomy file: Docker mount at /app/intent_taxonomy or repo checkout."""
    here = Path(__file__).resolve()
    candidates = [
        here.parents[2] / "intent_taxonomy" / "intent_labels_v1.yaml",  # .../fastapi_backend/intent_taxonomy
        here.parents[3] / "intent_taxonomy" / "intent_labels_v1.yaml",  # monorepo root
    ]
    for p in candidates:
        if p.is_file():
            return p
    return candidates[-1]


@lru_cache(maxsize=16)
def load_taxonomy_v1(path: str | None = None) -> IntentTaxonomyV1:
    """Load taxonomy from YAML (cached). Path defaults to repo intent_taxonomy file."""
    resolved = path or os.environ.get("INTENT_TAXONOMY_PATH") or str(_default_taxonomy_path())
    p = Path(resolved)
    if not p.is_file():
        raise FileNotFoundError(f"Intent taxonomy not found: {p}")
    with p.open(encoding="utf-8") as f:
        raw: dict[str, Any] = yaml.safe_load(f) or {}
    labels: List[str] = list(raw.get("candidate_labels") or [])
    return IntentTaxonomyV1(
        version=str(raw.get("version", "1")),
        confidence_threshold=float(raw.get("confidence_threshold", 0.35)),
        candidate_labels=tuple(labels),
    )


def is_routable_intent(intent: str, taxonomy: IntentTaxonomyV1 | None = None) -> bool:
    tx = taxonomy or load_taxonomy_v1()
    return intent in tx.routable_labels
