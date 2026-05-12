# app/api/health.py
"""Production-grade health check endpoint.

Probes every critical dependency (Database, Redis, OPA, Ollama, spaCy NLP)
and reports individual latency, overall system status, and uptime.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from typing import Any, Dict

import httpx
from fastapi import APIRouter, Request
from sqlalchemy import text

from app.core.config import settings
from app.infrastructure.db.session import AsyncSessionLocal

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Health"])

# ── Version — bump on each release ──────────────────────────────────────────
APP_VERSION = "1.0.0"


async def _check_database() -> Dict[str, Any]:
    """Probe PostgreSQL with a lightweight SELECT 1 query."""
    start = time.monotonic()
    try:
        async with AsyncSessionLocal() as session:
            await session.execute(text("SELECT 1"))
        latency = round((time.monotonic() - start) * 1000, 1)
        return {"status": "up", "latency_ms": latency}
    except Exception as exc:
        latency = round((time.monotonic() - start) * 1000, 1)
        logger.warning("[HealthCheck] Database probe failed: %s", exc)
        return {"status": "down", "latency_ms": latency, "error": str(exc)}


async def _check_redis() -> Dict[str, Any]:
    """Probe Redis with a PING command."""
    start = time.monotonic()
    try:
        import redis.asyncio as aioredis

        client = aioredis.from_url(settings.redis_url, decode_responses=True)
        await client.ping()
        await client.aclose()
        latency = round((time.monotonic() - start) * 1000, 1)
        return {"status": "up", "latency_ms": latency}
    except Exception as exc:
        latency = round((time.monotonic() - start) * 1000, 1)
        logger.warning("[HealthCheck] Redis probe failed: %s", exc)
        return {"status": "down", "latency_ms": latency, "error": str(exc)}


async def _check_opa() -> Dict[str, Any]:
    """Probe OPA with a health endpoint check."""
    start = time.monotonic()
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            resp = await client.get(f"{settings.opa_url}/health")
            resp.raise_for_status()
        latency = round((time.monotonic() - start) * 1000, 1)
        return {"status": "up", "latency_ms": latency}
    except Exception as exc:
        latency = round((time.monotonic() - start) * 1000, 1)
        logger.warning("[HealthCheck] OPA probe failed: %s", exc)
        return {"status": "down", "latency_ms": latency, "error": str(exc)}


async def _check_ollama() -> Dict[str, Any]:
    """Probe the Ollama LLM inference engine."""
    start = time.monotonic()
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get("http://ollama:11434/api/tags")
            resp.raise_for_status()
            models = resp.json().get("models", [])
        latency = round((time.monotonic() - start) * 1000, 1)
        return {
            "status": "up",
            "latency_ms": latency,
            "loaded_models": len(models),
        }
    except Exception as exc:
        latency = round((time.monotonic() - start) * 1000, 1)
        logger.warning("[HealthCheck] Ollama probe failed: %s", exc)
        return {"status": "down", "latency_ms": latency, "error": str(exc)}


def _check_spacy() -> Dict[str, Any]:
    """Verify the spaCy NLP model is loaded in memory."""
    try:
        from app.infrastructure.nlp.spacy_loader import get_nlp

        nlp = get_nlp()
        return {"status": "loaded", "model": nlp.meta.get("name", "unknown")}
    except Exception as exc:
        logger.warning("[HealthCheck] spaCy probe failed: %s", exc)
        return {"status": "not_loaded", "error": str(exc)}


@router.get("/health")
async def health_check(request: Request) -> Dict[str, Any]:
    """Deep health check — probes all platform dependencies.

    Returns an aggregate status plus individual component checks
    with latency measurements in milliseconds.
    """
    startup_time: float = getattr(request.app.state, "startup_time", None)
    uptime = round(time.time() - startup_time, 1) if startup_time else None

    # Run all async probes concurrently
    import asyncio

    db_check, redis_check, opa_check, ollama_check = await asyncio.gather(
        _check_database(),
        _check_redis(),
        _check_opa(),
        _check_ollama(),
    )

    # Sync check for spaCy (it's already loaded in memory)
    spacy_check = _check_spacy()

    checks = {
        "database": db_check,
        "redis": redis_check,
        "opa": opa_check,
        "ollama": ollama_check,
        "spacy_nlp": spacy_check,
    }

    # Overall status: "healthy" only if all critical deps are up
    critical_deps = [db_check, redis_check]
    all_critical_up = all(c.get("status") == "up" for c in critical_deps)
    overall = "healthy" if all_critical_up else "degraded"

    return {
        "status": overall,
        "version": APP_VERSION,
        "uptime_seconds": uptime,
        "checks": checks,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
