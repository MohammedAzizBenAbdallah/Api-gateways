# app/core/logging.py
"""Structured logging setup used across the backend."""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def setup_logging() -> None:
    """Configure global logging format for consistent structured output."""

    # Avoid double-configuring in reload scenarios.
    root_logger = logging.getLogger()
    if root_logger.handlers:
        return

    logging.basicConfig(
        level=logging.INFO,
        format="[%(name)s] %(levelname)s %(message)s",
    )

