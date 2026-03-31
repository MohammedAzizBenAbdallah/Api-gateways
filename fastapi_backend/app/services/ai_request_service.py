# app/services/ai_request_service.py
"""Orchestrate AI request lifecycle including streaming and persistence."""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime
from typing import Any, AsyncIterator, Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover
    from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import (
    ProviderError,
    ServiceNotFoundError,
    TenantIdMissingError,
    TenantNotAuthorizedError,
)
from app.infrastructure.ai_provider.ollama_client import chat as ollama_chat
from app.repositories.ai_request_repository import (
    create_ai_request,
    update_ai_request_status,
    update_resolved_sensitivity,
)
from app.repositories.ai_service_repository import get_ai_service_by_id
from app.repositories.permission_repository import check_tenant_service_permission_and_audit
from app.services.content_inspector_service import ContentInspectorService
from app.services.intent_cache_service import IntentCacheService


logger = logging.getLogger(__name__)


class AIRequestService:
    """Business orchestration for the AI request endpoint."""

    def __init__(
        self,
        *,
        intent_cache_service: IntentCacheService,
        content_inspector_service: ContentInspectorService,
        session_factory: Any,
    ) -> None:
        self._intent_cache_service = intent_cache_service
        self._content_inspector_service = content_inspector_service
        self._session_factory = session_factory

    async def _update_status_in_new_session(
        self,
        *,
        request_id: str,
        status: str,
        completed_at: Optional[datetime] = None,
        error_detail: Optional[str] = None,
    ) -> None:
        async with self._session_factory() as session:
            await update_ai_request_status(
                session,
                request_id=request_id,
                status=status,
                completed_at=completed_at,
                error_detail=error_detail,
            )

    async def submit_stream(
        self,
        *,
        db: "AsyncSession",
        current_user: Dict[str, Any],
        body: Any,
        nlp: Any,
    ) -> Dict[str, Any]:
        """Stream SSE events for an AI request."""
        request_id = str(uuid.uuid4())
        intent_name: str = body.intent
        environment: str = body.metadata.environment

        tenant_id = current_user.get("tenant_id")
        if not tenant_id:
            raise TenantIdMissingError()

        resolved_service_id = self._intent_cache_service.resolve_intent(intent_name)

        is_allowed = await check_tenant_service_permission_and_audit(
            db,
            tenant_id=tenant_id,
            service_id=resolved_service_id,
            intent=intent_name,
        )
        if not is_allowed:
            raise TenantNotAuthorizedError(tenant_id=tenant_id, service_id=resolved_service_id)

        service = await get_ai_service_by_id(db, service_id=resolved_service_id)
        if service is None:
            raise ServiceNotFoundError(service_id=resolved_service_id)

        # Create tracking record.
        try:
            await create_ai_request(
                db,
                request_id=request_id,
                tenant_id=tenant_id,
                intent=intent_name,
                resolved_service_id=resolved_service_id,
                sensitivity=body.metadata.sensitivity.value,
                environment=environment,
                status="received",
                started_at=datetime.utcnow(),
            )
        except Exception as exc:
            logger.exception("Failed to persist received request record: %s", exc)
            raise ProviderError("Failed to persist request record")

        # Resolve final sensitivity + PII types based on content.
        final_sensitivity, detected_pii_types = await self._content_inspector_service.inspect_content(
            body, nlp
        )
        if final_sensitivity.value != body.metadata.sensitivity.value:
            logger.warning(
                "[ContentInspector] Sensitivity upgraded %s → %s for request %s",
                body.metadata.sensitivity.value,
                final_sensitivity.value,
                request_id,
            )

        # Persist resolved sensitivity.
        await update_resolved_sensitivity(
            db,
            request_id=request_id,
            resolved_sensitivity=final_sensitivity.value,
        )

        messages: List[Dict[str, str]] = [
            {"role": m.role, "content": m.content} for m in body.payload.messages
        ]

        outbound_model = service.model_name
        outbound_provider_url = service.provider_url

        async def _event_stream() -> AsyncIterator[str]:
            first_token = True
            try:
                stream_iter = await ollama_chat(
                    provider_url=outbound_provider_url,
                    model=outbound_model,
                    messages=messages,
                    stream=True,
                )
                if stream_iter is None:
                    raise ProviderError("Provider stream returned no iterator")

                async for chunk in stream_iter:
                    token = chunk.get("token", "") or ""
                    done = bool(chunk.get("done", False))

                    if done:
                        yield (
                            "data: "
                            + json.dumps(
                                {
                                    "token": "",
                                    "done": True,
                                    "request_id": request_id,
                                    "resolved_service": resolved_service_id,
                                    "intent": intent_name,
                                    "resolved_sensitivity": final_sensitivity.value,
                                    "detected_pii_types": detected_pii_types,
                                }
                            )
                            + "\n\n"
                        )
                        await self._update_status_in_new_session(
                            request_id=request_id,
                            status="completed",
                            completed_at=datetime.utcnow(),
                        )
                        return

                    if token:
                        if first_token:
                            first_token = False
                            await self._update_status_in_new_session(
                                request_id=request_id,
                                status="streaming",
                            )
                        yield "data: " + json.dumps({"token": token, "done": False}) + "\n\n"
            except Exception as exc:
                logger.exception("SSE stream error: %s", exc)
                yield (
                    "data: "
                    + json.dumps({"error": f"Stream interrupted: {str(exc)}", "done": True})
                    + "\n\n"
                )
                await self._update_status_in_new_session(
                    request_id=request_id,
                    status="failed",
                    completed_at=datetime.utcnow(),
                    error_detail=str(exc),
                )

        return {"request_id": request_id, "stream": _event_stream()}

    async def submit_json(
        self,
        *,
        db: "AsyncSession",
        current_user: Dict[str, Any],
        body: Any,
        nlp: Any,
    ) -> Dict[str, Any]:
        """Submit an AI request and return JSON response."""
        request_id = str(uuid.uuid4())
        intent_name: str = body.intent
        environment: str = body.metadata.environment

        tenant_id = current_user.get("tenant_id")
        if not tenant_id:
            raise TenantIdMissingError()

        resolved_service_id = self._intent_cache_service.resolve_intent(intent_name)

        is_allowed = await check_tenant_service_permission_and_audit(
            db,
            tenant_id=tenant_id,
            service_id=resolved_service_id,
            intent=intent_name,
        )
        if not is_allowed:
            raise TenantNotAuthorizedError(tenant_id=tenant_id, service_id=resolved_service_id)

        service = await get_ai_service_by_id(db, service_id=resolved_service_id)
        if service is None:
            raise ServiceNotFoundError(service_id=resolved_service_id)

        try:
            await create_ai_request(
                db,
                request_id=request_id,
                tenant_id=tenant_id,
                intent=intent_name,
                resolved_service_id=resolved_service_id,
                sensitivity=body.metadata.sensitivity.value,
                environment=environment,
                status="received",
                started_at=datetime.utcnow(),
            )
        except Exception as exc:
            logger.exception("Failed to persist received request record: %s", exc)
            raise ProviderError("Failed to persist request record")

        final_sensitivity, _detected_pii_types = await self._content_inspector_service.inspect_content(
            body, nlp
        )
        if final_sensitivity.value != body.metadata.sensitivity.value:
            logger.warning(
                "[ContentInspector] Sensitivity upgraded %s → %s for request %s",
                body.metadata.sensitivity.value,
                final_sensitivity.value,
                request_id,
            )

        await update_resolved_sensitivity(
            db,
            request_id=request_id,
            resolved_sensitivity=final_sensitivity.value,
        )

        messages: List[Dict[str, str]] = [
            {"role": m.role, "content": m.content} for m in body.payload.messages
        ]

        outbound_body_model = service.model_name
        outbound_provider_url = service.provider_url

        try:
            start = datetime.utcnow()
            provider_data = await ollama_chat(
                provider_url=outbound_provider_url,
                model=outbound_body_model if service.provider_type == "ollama" else None,
                messages=messages,
                stream=False,
            )
            elapsed_ms = int((datetime.utcnow() - start).total_seconds() * 1000)
        except Exception as exc:
            logger.exception("Provider call failed: %s", exc)
            try:
                await self._update_status_in_new_session(
                    request_id=request_id,
                    status="failed",
                    completed_at=datetime.utcnow(),
                    error_detail=str(exc),
                )
            finally:
                raise ProviderError(f"Failed to connect to AI provider: {str(exc)}")

        await self._update_status_in_new_session(
            request_id=request_id,
            status="completed",
            completed_at=datetime.utcnow(),
        )

        # We do not have provider RTT from here (ollama_client currently returns JSON without timing metadata),
        # but we preserve the payload and a minimal debug header set in the router if needed.
        return {
            "data": {
                "request_id": request_id,
                "intent": intent_name,
                "resolved_service": resolved_service_id,
                "response": provider_data,
            },
            "response_headers": {
                "x-kong-proxy-latency": "1",
                "x-kong-upstream-latency": str(elapsed_ms),
                "x-ai-debug": f"intent={intent_name} service={resolved_service_id} model={service.model_name}",
            },
        }

