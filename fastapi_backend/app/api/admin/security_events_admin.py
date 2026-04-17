# app/api/admin/security_events_admin.py
"""Admin API for Security Events feed and Security Score computation."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, func, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.middleware import verify_kong_header
from app.core.security import get_current_user
from app.infrastructure.db.session import get_db_with_user
from app.models.security_event import SecurityEvent
from app.models.security_pattern import SecurityPattern

import httpx

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/admin/security",
    tags=["Admin - Security Operations"],
    dependencies=[Depends(verify_kong_header), Depends(get_current_user)],
)

KONG_ADMIN_URL = "http://kong-gateway:8001"


@router.get("/events")
async def list_security_events(
    limit: int = Query(50, le=200),
    event_type: Optional[str] = Query(None),
    decision: Optional[str] = Query(None),
    db: AsyncSession = Depends(get_db_with_user),
) -> List[Dict[str, Any]]:
    """Return recent security events for the live threat feed."""
    query = select(SecurityEvent).order_by(desc(SecurityEvent.created_at)).limit(limit)

    if event_type:
        query = query.where(SecurityEvent.event_type == event_type)
    if decision:
        query = query.where(SecurityEvent.decision == decision)

    result = await db.execute(query)
    events = result.scalars().all()

    return [
        {
            "id": e.id,
            "event_type": e.event_type,
            "tenant_id": e.tenant_id,
            "request_id": e.request_id,
            "score": e.score,
            "decision": e.decision,
            "matched_patterns": e.matched_patterns,
            "redacted_types": e.redacted_types,
            "redaction_count": e.redaction_count,
            "created_at": e.created_at.isoformat() if e.created_at else None,
        }
        for e in events
    ]


@router.get("/score")
async def get_security_score(
    db: AsyncSession = Depends(get_db_with_user),
) -> Dict[str, Any]:
    """Compute a 0-100 platform security health score from live data."""
    breakdown = {}
    score = 0

    # 1. Prompt injection patterns loaded (max 20 pts)
    pattern_count_result = await db.execute(
        select(func.count()).select_from(SecurityPattern).where(SecurityPattern.is_active == True)
    )
    pattern_count = pattern_count_result.scalar() or 0
    pts = min(20, pattern_count * 2)  # 2 pts per pattern, max 20
    breakdown["ai_patterns"] = {"points": pts, "max": 20, "detail": f"{pattern_count} active patterns"}
    score += pts

    # 2-5. Kong plugins (max 50 pts total)
    kong_plugin_pts = 0
    kong_details = []
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(f"{KONG_ADMIN_URL}/plugins")
            if resp.status_code == 200:
                plugins = resp.json().get("data", [])
                active_names = [p["name"] for p in plugins if p.get("enabled", True)]

                # General plugin coverage (max 20)
                plugin_pts = min(20, len(active_names) * 5)
                kong_plugin_pts += plugin_pts
                kong_details.append(f"{len(active_names)} active plugins")

                # Rate limiting bonus (+10)
                if "rate-limiting" in active_names:
                    kong_plugin_pts += 10
                    kong_details.append("rate-limiting ✓")

                # IP restriction bonus (+10)
                if "ip-restriction" in active_names:
                    kong_plugin_pts += 10
                    kong_details.append("ip-restriction ✓")

                # CORS bonus (+10)
                if "cors" in active_names:
                    kong_plugin_pts += 10
                    kong_details.append("cors ✓")
    except Exception:
        kong_details.append("Kong unreachable")

    kong_plugin_pts = min(50, kong_plugin_pts)
    breakdown["kong_edge"] = {"points": kong_plugin_pts, "max": 50, "detail": ", ".join(kong_details)}
    score += kong_plugin_pts

    # 6. PII redaction engine active (10 pts — always on since OutputGuardService is instantiated)
    breakdown["pii_redaction"] = {"points": 10, "max": 10, "detail": "OutputGuard active"}
    score += 10

    # 7. Recent attack defense (max 20 pts)
    now = datetime.utcnow()
    day_ago = now - timedelta(days=1)
    blocked_result = await db.execute(
        select(func.count()).select_from(SecurityEvent).where(
            SecurityEvent.created_at >= day_ago,
            SecurityEvent.decision == "blocked"
        )
    )
    blocked_24h = blocked_result.scalar() or 0

    total_events_result = await db.execute(
        select(func.count()).select_from(SecurityEvent).where(
            SecurityEvent.created_at >= day_ago
        )
    )
    total_24h = total_events_result.scalar() or 0

    if total_24h == 0:
        defense_pts = 20  # No attacks = full score
        defense_detail = "No threats in 24h"
    else:
        defense_rate = (blocked_24h / total_24h) * 100
        defense_pts = int(min(20, defense_rate / 5))
        defense_detail = f"{blocked_24h}/{total_24h} threats blocked ({defense_rate:.0f}%)"

    breakdown["threat_defense"] = {"points": defense_pts, "max": 20, "detail": defense_detail}
    score += defense_pts

    # Clamp
    score = min(100, score)

    if score >= 80:
        grade = "EXCELLENT"
    elif score >= 50:
        grade = "MODERATE"
    else:
        grade = "CRITICAL"

    return {
        "score": score,
        "grade": grade,
        "breakdown": breakdown,
    }
