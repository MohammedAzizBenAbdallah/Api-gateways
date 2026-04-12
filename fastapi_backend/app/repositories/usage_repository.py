# app/repositories/usage_repository.py
from __future__ import annotations
import logging
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from app.models.usage import UsageTokenLog

logger = logging.getLogger(__name__)

async def create_usage_log(
    session: AsyncSession,
    *,
    request_id: str,
    tenant_id: str,
    service_id: str,
    model_name: Optional[str],
    input_tokens: int,
    output_tokens: int,
) -> UsageTokenLog:
    """Persist AI token usage metrics to the database."""
    total_tokens = input_tokens + output_tokens
    
    # Placeholder cost calculation: $0.002 per 1k tokens
    cost_estimate = (total_tokens / 1000.0) * 0.002
    
    usage_log = UsageTokenLog(
        request_id=request_id,
        tenant_id=tenant_id,
        service_id=service_id,
        model_name=model_name,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        total_tokens=total_tokens,
        cost_estimate=cost_estimate,
    )
    
    session.add(usage_log)
    await session.commit()
    return usage_log
