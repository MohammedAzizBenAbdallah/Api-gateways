# app/api/admin/metrics.py
import logging
from datetime import datetime, timedelta
from typing import Dict, Any

from fastapi import APIRouter, Depends
from sqlalchemy import select, func, text, case
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.middleware import verify_kong_header
from app.core.security import get_current_user
from app.infrastructure.db.session import get_db, get_db_with_user
from app.models.ai_request import AIRequestRecord
from app.models.ai_service import AIService
from app.models.usage import UsageTokenLog

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/admin/metrics",
    tags=["Admin Metrics"],
    dependencies=[Depends(verify_kong_header), Depends(get_current_user)],
)

@router.get("")
async def get_dashboard_metrics(db: AsyncSession = Depends(get_db_with_user)) -> Dict[str, Any]:
    """Retrieve realtime platform aggregation metrics."""
    now = datetime.utcnow()
    yesterday = now - timedelta(days=1)
    
    # Base queries
    # 1. Total requests (24h) and success rate
    query_24h = select(
        func.count().label("total"),
        func.sum(case((AIRequestRecord.status == "completed", 1), else_=0)).label("successes")
    ).where(AIRequestRecord.started_at >= yesterday)
    
    res_24h = await db.execute(query_24h)
    row_24h = res_24h.fetchone()
    total_24h = row_24h.total or 0
    successes_24h = row_24h.successes or 0
    success_rate = (successes_24h / total_24h * 100) if total_24h > 0 else 100.0

    # 2. Top Intent
    query_intent = select(
        AIRequestRecord.intent,
        func.count(AIRequestRecord.intent).label("cnt")
    ).where(AIRequestRecord.started_at >= yesterday).group_by(AIRequestRecord.intent).order_by(text("cnt DESC")).limit(1)
    
    res_intent = await db.execute(query_intent)
    row_intent = res_intent.fetchone()
    top_intent = f"{row_intent.intent} (Top)" if row_intent else "N/A"

    # 3. Security Events
    # Blocked by Policy
    query_blocked = select(func.count()).where(AIRequestRecord.status == "denied")
    res_blocked = await db.execute(query_blocked)
    blocked_count = res_blocked.scalar() or 0

    # PII Upgrades
    query_pii = select(func.count()).where(
        AIRequestRecord.sensitivity != AIRequestRecord.resolved_sensitivity,
        AIRequestRecord.resolved_sensitivity != None
    )
    res_pii = await db.execute(query_pii)
    pii_upgrades = res_pii.scalar() or 0

    # 4. Routing Decisions (Cloud vs Edge Traffic)
    query_routing = select(
        AIService.service_type,
        func.count(AIRequestRecord.request_id).label("cnt")
    ).select_from(AIRequestRecord).join(
        AIService,
        AIRequestRecord.resolved_service_id == AIService.service_id,
        isouter=True
    ).where(
        AIService.service_type != None
    ).group_by(AIService.service_type)
    
    res_routing = await db.execute(query_routing)
    routing_rows = res_routing.fetchall()
    cloud_traffic = 0
    edge_traffic = 0
    total_routed = 0
    for row in routing_rows:
        total_routed += row.cnt
        if row.service_type == "cloud":
            cloud_traffic += row.cnt
        else:
            edge_traffic += row.cnt
            
    cloud_pct = (cloud_traffic / total_routed * 100) if total_routed > 0 else 0
    edge_pct = (edge_traffic / total_routed * 100) if total_routed > 0 else 0

    # 5. System Health / Pipeline Latency average (ms)
    query_latency = select(
        func.avg(
            func.extract('epoch', AIRequestRecord.completed_at) - 
            func.extract('epoch', AIRequestRecord.started_at)
        )
    ).where(AIRequestRecord.status == "completed", AIRequestRecord.completed_at != None)
    res_latency = await db.execute(query_latency)
    avg_latency_sec = res_latency.scalar()
    avg_latency_ms = int(avg_latency_sec * 1000) if avg_latency_sec else 0

    # 6. Usage & Cost
    query_consumers = select(
        UsageTokenLog.tenant_id,
        func.sum(UsageTokenLog.total_tokens).label("tkns")
    ).where(UsageTokenLog.created_at >= yesterday).group_by(UsageTokenLog.tenant_id).order_by(text("tkns DESC")).limit(1)
    res_cons = await db.execute(query_consumers)
    row_cons = res_cons.fetchone()
    top_consumer = row_cons.tenant_id if row_cons else "No traffic"

    query_cost = select(func.sum(UsageTokenLog.cost_estimate)).where(UsageTokenLog.created_at >= yesterday)
    res_cost = await db.execute(query_cost)
    total_cost = res_cost.scalar() or 0.0

    return {
        "health": {
            "total_requests": total_24h,
            "success_rate": round(success_rate, 1),
            "top_intent": top_intent
        },
        "security": {
            "blocked": blocked_count,
            "pii_upgrades": pii_upgrades,
            "prompt_injections": 0  # Placeholder, not natively tracked as injection enum yet
        },
        "routing": {
            "cloud_percentage": round(cloud_pct, 1),
            "edge_percentage": round(edge_pct, 1),
            "denied_pre_proxy": blocked_count  # Simple equivalent mapping
        },
        "system": {
            "backend_latency_ms": avg_latency_ms,
        },
        "cost": {
            "top_consumer": top_consumer,
            "projected_cost": float(total_cost)
        }
    }
