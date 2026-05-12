# app/core/logging.py
"""Structured logging setup with Correlation ID injection.

Every log line automatically includes the current request's correlation ID,
enabling end-to-end distributed tracing from Kong → FastAPI → Database.

Example output:
    13:05:22 I [app.services.ai_request_service] [cid=a1b2c3d4-...] Processing request
"""

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


class CorrelationIdFilter(logging.Filter):
    """Logging filter that injects the current correlation ID into every record.

    Reads from the ContextVar set by CorrelationIdMiddleware. If no request
    context is active (e.g., during startup), defaults to '-'.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        from app.core.middleware import correlation_id_ctx

        record.correlation_id = correlation_id_ctx.get("-")
        return True


def setup_logging() -> None:
    """Configure global logging format with correlation ID support."""

    # Avoid double-configuring in reload scenarios.
    root_logger = logging.getLogger()
    if root_logger.handlers:
        return

    # Add the correlation ID filter to the root logger
    cid_filter = CorrelationIdFilter()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname).1s [%(name)s] [cid=%(correlation_id)s] %(message)s",
        datefmt="%H:%M:%S",
    )

    # Attach the filter to all handlers
    for handler in root_logger.handlers:
        handler.addFilter(cid_filter)

    # Suppress noisy third-party loggers.
    for name in _NOISY_LOGGERS:
        logging.getLogger(name).setLevel(logging.WARNING)
