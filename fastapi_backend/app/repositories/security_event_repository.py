# app/repositories/security_event_repository.py
"""Persistence for security events (prompt injection blocks, PII redactions)."""

from __future__ import annotations

import json
import logging
from typing import List, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.security_event import SecurityEvent

logger = logging.getLogger(__name__)


async def create_security_event(
    session: AsyncSession,
    *,
    event_type: str,
    tenant_id: str,
    request_id: Optional[str] = None,
    prompt_hash: Optional[str] = None,
    matched_patterns: Optional[List[str]] = None,
    score: Optional[float] = None,
    decision: str,
    redacted_types: Optional[List[str]] = None,
    redaction_count: int = 0,
    metadata_extra: Optional[dict] = None,
) -> SecurityEvent:
    """Create a security event audit record.

    Privacy guarantee: prompt_hash is a SHA-256 digest — the original
    prompt text is NEVER persisted.
    """
    event = SecurityEvent(
        event_type=event_type,
        tenant_id=tenant_id,
        request_id=request_id,
        prompt_hash=prompt_hash,
        matched_patterns=json.dumps(matched_patterns) if matched_patterns else None,
        score=score,
        decision=decision,
        redacted_types=json.dumps(redacted_types) if redacted_types else None,
        redaction_count=redaction_count,
        metadata_extra=json.dumps(metadata_extra) if metadata_extra else None,
    )
    session.add(event)
    await session.commit()

    logger.info(
        "[SecurityEvent] Logged event_type=%s tenant=%s decision=%s",
        event_type,
        tenant_id,
        decision,
    )
    return event
