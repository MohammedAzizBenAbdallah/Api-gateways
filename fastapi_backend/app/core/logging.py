# app/core/logging.py
"""Structured logging setup used across the backend."""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

# Third-party loggers that generate excessive noise at INFO/DEBUG level.
_NOISY_LOGGERS = (
    "sqlalchemy.engine",
    "sqlalchemy.pool",
    "httpx",
    "httpcore",
    "uvicorn.access",
    "asyncio",
    "aiosqlite",
)


def setup_logging() -> None:
    """Configure global logging format for consistent structured output."""

    # Avoid double-configuring in reload scenarios.
    root_logger = logging.getLogger()
    if root_logger.handlers:
        return

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname).1s [%(name)s] %(message)s",
        datefmt="%H:%M:%S",
    )

    # Suppress noisy third-party loggers.
    for name in _NOISY_LOGGERS:
        logging.getLogger(name).setLevel(logging.WARNING)

