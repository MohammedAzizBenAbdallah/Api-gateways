# app/infrastructure/nlp/spacy_loader.py
"""Load spaCy model once and expose it as a dependency."""

from __future__ import annotations

import logging
from functools import lru_cache
from typing import Any

import spacy
from fastapi import Depends

logger = logging.getLogger(__name__)

SPACY_MODEL_NAME = "en_core_web_sm"


@lru_cache(maxsize=1)
def load_spacy_model() -> Any:
    """Load and cache the spaCy model in-process."""
    try:
        return spacy.load(SPACY_MODEL_NAME)
    except OSError as exc:
        raise RuntimeError(
            "spaCy model 'en_core_web_sm' is not installed. "
            "Run: python -m spacy download en_core_web_sm"
        ) from exc


def get_nlp() -> Any:
    """FastAPI dependency that returns the cached spaCy NLP object."""
    nlp = load_spacy_model()
    logger.info("[spacy_loader] spaCy model loaded: %s", SPACY_MODEL_NAME)
    return nlp

