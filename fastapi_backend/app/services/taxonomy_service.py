"""Load and validate enterprise intent taxonomy from YAML (ORK-015)."""

from __future__ import annotations

import logging
import os
from typing import Dict, List, Set

import yaml
from pydantic import BaseModel, ConfigDict, Field

from app.core.exceptions import IntentNotFoundError

logger = logging.getLogger(__name__)


class TaxonomyIntentEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    label: str
    service_id: str
    description: str = ""
    examples: List[str] = Field(default_factory=list)


class TaxonomyFileSchema(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: str = "1.0.0"
    intents: List[TaxonomyIntentEntry]


class TaxonomyService:
    """In-memory taxonomy: authoritative list of intent labels + version."""

    def __init__(self, *, file_path: str) -> None:
        self._file_path = file_path
        self._version = "unknown"
        self._labels: Set[str] = set()
        self._intent_service: Dict[str, str] = {}
        self._loaded = False

    def load(self) -> None:
        path = self._file_path
        if not os.path.isabs(path):
            path = os.path.join(os.getcwd(), self._file_path)
        if not os.path.exists(path):
            raise FileNotFoundError(f"Taxonomy file not found: {path}")
        with open(path, "r", encoding="utf-8") as f:
            raw = yaml.safe_load(f)
        data = TaxonomyFileSchema.model_validate(raw)
        self._version = data.version
        self._labels = {e.label for e in data.intents}
        self._intent_service = {e.label: e.service_id for e in data.intents}
        self._loaded = True
        logger.info(
            "[Taxonomy] Loaded version %s with %d intents",
            self._version,
            len(self._labels),
        )

    @property
    def version(self) -> str:
        return self._version

    def assert_intent_allowed(self, intent_name: str) -> None:
        if not self._loaded:
            raise RuntimeError("TaxonomyService not loaded")
        if intent_name not in self._labels:
            raise IntentNotFoundError(
                intent_name=intent_name,
                taxonomy_version=self._version,
            )

    def allowed_labels(self) -> Set[str]:
        return set(self._labels)

    def default_service_for_intent(self, intent_name: str) -> str | None:
        """Optional hint from taxonomy YAML (DB mapping may override)."""
        return self._intent_service.get(intent_name)
