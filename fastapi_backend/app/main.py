# app/main.py
from __future__ import annotations
"""FastAPI application factory wiring routers and application services."""
print("[DEBUG] Loading main.py...")

import asyncio
import logging
import os
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.admin.intent_mappings import router as admin_intent_mappings_router
from app.api.admin.services import router as admin_services_router
from app.api.ai import router as ai_router
from app.core.config import settings
from app.core.middleware import verify_kong_header
from app.core.security import get_current_user
from app.core.logging import setup_logging
from app.infrastructure.ai_provider.ollama_client import chat as _  # noqa: F401
from app.infrastructure.db.session import AsyncSessionLocal
from app.infrastructure.nlp.spacy_loader import get_nlp
from app.services.ai_request_service import AIRequestService
from app.services.content_inspector_service import ContentInspectorService
from app.services.intent_cache_service import IntentCacheService
from app.services.intent_mappings_service import IntentMappingsService
from app.services.policy_service import PolicyService

setup_logging()
logger = logging.getLogger(__name__)


content_inspector_service = ContentInspectorService()
intent_cache_service = IntentCacheService(session_factory=AsyncSessionLocal)
policy_service = PolicyService()


def _build_ai_request_service() -> AIRequestService:
    return AIRequestService(
        intent_cache_service=intent_cache_service,
        content_inspector_service=content_inspector_service,
        policy_service=policy_service,
        session_factory=AsyncSessionLocal,
    )


def _build_intent_mappings_service() -> IntentMappingsService:
    return IntentMappingsService(intent_cache_service=intent_cache_service)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Load and validate governance policies (fail-fast if invalid)
    policy_path = os.path.join(os.getcwd(), settings.policy_file_path)
    logger.info("Initializing Policy Engine from %s", policy_path)
    policy_service.load_policies(policy_path)

    # Fail fast if required external dependencies (spaCy model) are missing.
    _ = get_nlp()

    # Initialize cache from DB.
    await intent_cache_service.initialize()

    # Start background refresh; cancel on shutdown.
    task = asyncio.create_task(intent_cache_service.start_background_refresh())
    try:
        yield
    finally:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass


def create_app() -> FastAPI:
    """Create the FastAPI application instance."""
    app = FastAPI(
        title="Kong AI Proxy Platform (FastAPI)",
        lifespan=lifespan,
    )

    app.state.intent_cache_service = intent_cache_service
    app.state.ai_request_service = _build_ai_request_service()
    app.state.intent_mappings_service = _build_intent_mappings_service()
    app.state.policy_service = policy_service

    app.add_middleware(
        CORSMiddleware,
        allow_origins=[settings.cors_origin],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Register Domain Routers (Fastest match)
    app.include_router(ai_router, prefix="/api")
    app.include_router(admin_intent_mappings_router, prefix="/api")
    app.include_router(admin_services_router, prefix="/api")

    @app.get("/", tags=["Health"])
    async def root() -> dict:
        return {"message": "FastAPI AI Platform Backend is running. Access via /api/"}

    @app.get("/api/", tags=["Health"])
    async def api_root() -> dict:
        return {"message": "hello world from Python (FastAPI)!"}

    @app.get(
        "/api/documents",
        tags=["Data"],
        dependencies=[Depends(verify_kong_header)],
    )
    async def get_documents(user: dict = Depends(get_current_user)) -> dict:
        email = user.get("email", "unknown")
        return {
            "message": "Documents",
            "client": email,
            "data": [
                {"id": 1, "name": f"{email} user Document 1"},
                {"id": 2, "name": f"{email} user Document 2"},
                {"id": 3, "name": f"{email} user Document 3"},
            ],
        }

    @app.get(
        "/api/admin",
        tags=["Data"],
        dependencies=[Depends(verify_kong_header)],
    )
    async def get_admin(user: dict = Depends(get_current_user)) -> dict:
        email = user.get("email", "unknown")
        return {
            "message": "admin documents",
            "client": email,
            "data": [
                {"id": 1, "name": f"{email} admin Document 1"},
                {"id": 2, "name": f"{email} admin Document 2"},
                {"id": 3, "name": f"{email} admin Document 3"},
            ],
        }

    return app


app = create_app()
