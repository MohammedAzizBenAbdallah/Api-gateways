"""Load intent taxonomy YAML (mirrors production intent_classifier_service)."""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, List

import yaml

UNCLASSIFIED = "unclassified"


@dataclass(frozen=True)
class Taxonomy:
    version: str
    confidence_threshold: float
    candidate_labels: tuple[str, ...]
    nli_phrases: tuple[str, ...]
    hypothesis_template: str


@lru_cache(maxsize=4)
def load_taxonomy(path: str) -> Taxonomy:
    p = Path(path)
    if not p.is_file():
        raise FileNotFoundError(f"Taxonomy file missing: {path}")
    with p.open(encoding="utf-8") as f:
        raw: dict[str, Any] = yaml.safe_load(f) or {}
    labels: List[str] = list(raw.get("candidate_labels") or [])
    hypotheses_map: dict[str, Any] = dict(raw.get("label_hypotheses") or {})
    phrases: List[str] = []
    for lab in labels:
        ph = hypotheses_map.get(lab)
        if isinstance(ph, str) and ph.strip():
            phrases.append(ph.strip())
        else:
            phrases.append(lab.replace("_", " "))
    hyp_tmpl = str(raw.get("hypothesis_template") or "The user is mainly looking for {}.")
    if "{}" not in hyp_tmpl:
        hyp_tmpl = "The user is mainly looking for {}."
    return Taxonomy(
        version=str(raw.get("version", "1")),
        confidence_threshold=float(raw.get("confidence_threshold", 0.35)),
        candidate_labels=tuple(labels),
        nli_phrases=tuple(phrases),
        hypothesis_template=hyp_tmpl,
    )
