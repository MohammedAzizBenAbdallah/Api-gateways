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

from sqlalchemy import text

from app.core.exceptions import (
    ProviderError,
    ServiceNotFoundError,
    TenantIdMissingError,
    TenantNotAuthorizedError,
    PolicyViolationError,
    QuotaExceededError,
    SecurityViolationError,
)
from app.repositories.usage_repository import create_usage_log as _create_usage_log
from app.infrastructure.ai_provider.ollama_client import chat as ollama_chat
from app.repositories.ai_request_repository import (
    create_ai_request,
    update_ai_request_status,
    update_resolved_sensitivity,
)
from app.repositories.ai_service_repository import get_ai_service_by_id
from app.repositories.permission_repository import check_tenant_service_permission_and_audit
from app.repositories.policy_audit_repository import create_policy_audit_log
from app.repositories.security_event_repository import create_security_event
from app.services.content_inspector_service import ContentInspectorService
from app.services.intent_cache_service import IntentCacheService
from app.services.output_guard_service import OutputGuardService
from app.services.policy_service import PolicyService
from app.services.prompt_security_service import PromptSecurityService
from app.services.quota_service import QuotaService


logger = logging.getLogger(__name__)


class AIRequestService:
    """Business orchestration for the AI request endpoint."""

    def __init__(
        self,
        *,
        intent_cache_service: IntentCacheService,
        content_inspector_service: ContentInspectorService,
        policy_service: PolicyService,
        quota_service: QuotaService,
        prompt_security_service: PromptSecurityService,
        output_guard_service: OutputGuardService,
        session_factory: Any,
    ) -> None:
        self._intent_cache_service = intent_cache_service
        self._content_inspector_service = content_inspector_service
        self._policy_service = policy_service
        self._quota_service = quota_service
        self._prompt_security = prompt_security_service
        self._output_guard = output_guard_service
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
            from sqlalchemy import text
            await session.execute(text("SELECT set_config('app.is_admin', 'true', true)"))
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

        # ── Quota Check (Redis) ──
        has_quota = await self._quota_service.check_quota(tenant_id)
        if not has_quota:
            logger.warning("[QuotaEngine] Tenant %s exceeded token quota", tenant_id)
            raise QuotaExceededError(tenant_id=tenant_id)

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

        # Policy Evaluation
        evaluation_results = []
        try:
            evaluation_results = self._policy_service.evaluate({
                "sensitivity": final_sensitivity,
                "tenant": tenant_id,
                "service_type": getattr(service, "service_type", "on-prem")
            })
        except PolicyViolationError as exc:
            evaluation_results = exc.results
            # Log results to DB before re-raising
            for res in evaluation_results:
                await create_policy_audit_log(
                    db,
                    request_id=request_id,
                    policy_id=res.policy_id,
                    effect=res.effect.value,
                    decision=res.decision,
                    context={
                        "sensitivity": final_sensitivity.value,
                        "tenant": tenant_id,
                        "service_type": getattr(service, "service_type", "on-prem")
                    }
                )
            raise
        
        # Log successful matches
        for res in evaluation_results:
            await create_policy_audit_log(
                db,
                request_id=request_id,
                policy_id=res.policy_id,
                effect=res.effect.value,
                decision=res.decision,
                context={
                    "sensitivity": final_sensitivity.value,
                    "tenant": tenant_id,
                    "service_type": getattr(service, "service_type", "on-prem")
                }
            )

        messages: List[Dict[str, str]] = [
            {"role": m.role, "content": m.content} for m in body.payload.messages
        ]

        # ── Prompt Security Scan (Input Shield) ──
        scan_result = self._prompt_security.scan_messages(messages)
        if scan_result.is_blocked:
            # Log security event before blocking
            async with self._session_factory() as sec_session:
                await sec_session.execute(text("SELECT set_config('app.is_admin', 'true', true)"))
                await create_security_event(
                    sec_session,
                    event_type="prompt_injection",
                    tenant_id=tenant_id,
                    request_id=request_id,
                    prompt_hash=scan_result.prompt_hash,
                    matched_patterns=scan_result.matched_patterns,
                    score=scan_result.total_score,
                    decision="blocked",
                )
            await self._update_status_in_new_session(
                request_id=request_id,
                status="blocked",
                completed_at=datetime.utcnow(),
                error_detail=f"Prompt injection detected: {scan_result.matched_patterns}",
            )
            raise SecurityViolationError(
                prompt_hash=scan_result.prompt_hash,
                matched_patterns=scan_result.matched_patterns,
                score=scan_result.total_score,
            )
        elif scan_result.matched_patterns:
            # Low-score match: allow but log for auditing
            async with self._session_factory() as sec_session:
                await sec_session.execute(text("SELECT set_config('app.is_admin', 'true', true)"))
                await create_security_event(
                    sec_session,
                    event_type="prompt_injection",
                    tenant_id=tenant_id,
                    request_id=request_id,
                    prompt_hash=scan_result.prompt_hash,
                    matched_patterns=scan_result.matched_patterns,
                    score=scan_result.total_score,
                    decision="allowed",
                )

        outbound_model = service.model_name
        outbound_provider_url = service.provider_url

        # ── Initialization Pulse ──
        # Send an immediate empty packet to trigger frontend typing dots.
        # This prevents the UI from "hanging" while waiting for Ollama to load the model.
        async def _event_stream() -> AsyncIterator[str]:
            yield "data: " + json.dumps({"token": "", "done": False}) + "\n\n"
            
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

                carry_buffer = ""
                async for chunk in stream_iter:
                    token = chunk.get("token", "") or ""
                    done = bool(chunk.get("done", False))

                    if token and not done:
                        if first_token:
                            first_token = False
                            await self._update_status_in_new_session(
                                request_id=request_id,
                                status="streaming",
                            )
                        # ── Output Guard: windowed PII redaction ──
                        safe_text, carry_buffer = self._output_guard.redact_stream_chunk(
                            token, carry_buffer
                        )
                        if safe_text:
                            yield "data: " + json.dumps({"token": safe_text, "done": False}) + "\n\n"

                    if done:
                        # Extract usage info if available
                        usage = chunk.get("usage")
                        current_quota = None
                        
                        if usage:
                            prompt_tokens = usage.get("prompt_eval_count", 0)
                            eval_tokens = usage.get("eval_count", 0)
                            
                            # Persist usage to Postgres
                            async with self._session_factory() as session:
                                await session.execute(text("SELECT set_config('app.is_admin', 'true', true)"))
                                await _create_usage_log(
                                    session,
                                    request_id=request_id,
                                    tenant_id=tenant_id,
                                    service_id=resolved_service_id,
                                    model_name=outbound_model,
                                    input_tokens=prompt_tokens,
                                    output_tokens=eval_tokens
                                )
                            
                            # Update Redis usage
                            await self._quota_service.increment_usage(tenant_id, prompt_tokens + eval_tokens)
                            
                        # Fetch latest quota status for push (regardless of current request usage)
                        current_quota = await self._quota_service.get_quota_status(tenant_id)

                        # Flush remaining carry buffer with redaction
                        final_token = carry_buffer + (token or "")
                        if final_token:
                            final_redacted = self._output_guard.redact(final_token)
                            final_token = final_redacted.redacted_text
                            if final_redacted.redaction_count > 0:
                                async with self._session_factory() as sec_session:
                                    await sec_session.execute(text("SELECT set_config('app.is_admin', 'true', true)"))
                                    await create_security_event(
                                        sec_session,
                                        event_type="pii_redaction",
                                        tenant_id=tenant_id,
                                        request_id=request_id,
                                        decision="redacted",
                                        redacted_types=final_redacted.redacted_types,
                                        redaction_count=final_redacted.redaction_count,
                                    )

                        yield (
                            "data: "
                            + json.dumps(
                                {
                                    "token": final_token,
                                    "done": True,
                                    "request_id": request_id,
                                    "resolved_service": resolved_service_id,
                                    "intent": intent_name,
                                    "resolved_sensitivity": final_sensitivity.value,
                                    "detected_pii_types": detected_pii_types,
                                    "usage": usage,
                                    "quota": current_quota
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

        # ── Quota Check (Redis) ──
        has_quota = await self._quota_service.check_quota(tenant_id)
        if not has_quota:
            logger.warning("[QuotaEngine] Tenant %s exceeded token quota", tenant_id)
            raise QuotaExceededError(tenant_id=tenant_id)

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

        # Policy Evaluation
        evaluation_results = []
        try:
            evaluation_results = self._policy_service.evaluate({
                "sensitivity": final_sensitivity,
                "tenant": tenant_id,
                "service_type": getattr(service, "service_type", "on-prem")
            })
        except PolicyViolationError as exc:
            evaluation_results = exc.results
            for res in evaluation_results:
                await create_policy_audit_log(
                    db,
                    request_id=request_id,
                    policy_id=res.policy_id,
                    effect=res.effect.value,
                    decision=res.decision,
                    context={
                        "sensitivity": final_sensitivity.value,
                        "tenant": tenant_id,
                        "service_type": getattr(service, "service_type", "on-prem")
                    }
                )
            raise
        
        for res in evaluation_results:
            await create_policy_audit_log(
                db,
                request_id=request_id,
                policy_id=res.policy_id,
                effect=res.effect.value,
                decision=res.decision,
                context={
                    "sensitivity": final_sensitivity.value,
                    "tenant": tenant_id,
                    "service_type": getattr(service, "service_type", "on-prem")
                }
            )

        messages: List[Dict[str, str]] = [
            {"role": m.role, "content": m.content} for m in body.payload.messages
        ]

        # ── Prompt Security Scan (Input Shield) ──
        scan_result = self._prompt_security.scan_messages(messages)
        if scan_result.is_blocked:
            async with self._session_factory() as sec_session:
                await sec_session.execute(text("SELECT set_config('app.is_admin', 'true', true)"))
                await create_security_event(
                    sec_session,
                    event_type="prompt_injection",
                    tenant_id=tenant_id,
                    request_id=request_id,
                    prompt_hash=scan_result.prompt_hash,
                    matched_patterns=scan_result.matched_patterns,
                    score=scan_result.total_score,
                    decision="blocked",
                )
            await self._update_status_in_new_session(
                request_id=request_id,
                status="blocked",
                completed_at=datetime.utcnow(),
                error_detail=f"Prompt injection detected: {scan_result.matched_patterns}",
            )
            raise SecurityViolationError(
                prompt_hash=scan_result.prompt_hash,
                matched_patterns=scan_result.matched_patterns,
                score=scan_result.total_score,
            )
        elif scan_result.matched_patterns:
            async with self._session_factory() as sec_session:
                await sec_session.execute(text("SELECT set_config('app.is_admin', 'true', true)"))
                await create_security_event(
                    sec_session,
                    event_type="prompt_injection",
                    tenant_id=tenant_id,
                    request_id=request_id,
                    prompt_hash=scan_result.prompt_hash,
                    matched_patterns=scan_result.matched_patterns,
                    score=scan_result.total_score,
                    decision="allowed",
                )

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

        # Usage tracking for JSON
        usage = provider_data.get("usage", {})
        prompt_tokens = usage.get("prompt_eval_count", 0)
        eval_tokens = usage.get("eval_count", 0)
        
        async with self._session_factory() as session:
            await session.execute(text("SELECT set_config('app.is_admin', 'true', true)"))
            await _create_usage_log(
                session,
                request_id=request_id,
                tenant_id=tenant_id,
                service_id=resolved_service_id,
                model_name=outbound_body_model,
                input_tokens=prompt_tokens,
                output_tokens=eval_tokens
            )
        
        await self._quota_service.increment_usage(tenant_id, prompt_tokens + eval_tokens)
        
        # Push latest quota status
        current_quota = await self._quota_service.get_quota_status(tenant_id)

        await self._update_status_in_new_session(
            request_id=request_id,
            status="completed",
            completed_at=datetime.utcnow(),
        )

        # ── Output Guard: Full PII redaction on JSON response ──
        response_text = provider_data.get("message", {}).get("content", "")
        if response_text:
            redaction_result = self._output_guard.redact(response_text)
            if redaction_result.redaction_count > 0:
                # Replace the response content with redacted version
                if "message" in provider_data:
                    provider_data["message"]["content"] = redaction_result.redacted_text
                async with self._session_factory() as sec_session:
                    await sec_session.execute(text("SELECT set_config('app.is_admin', 'true', true)"))
                    await create_security_event(
                        sec_session,
                        event_type="pii_redaction",
                        tenant_id=tenant_id,
                        request_id=request_id,
                        decision="redacted",
                        redacted_types=redaction_result.redacted_types,
                        redaction_count=redaction_result.redaction_count,
                    )

        return {
            "data": {
                "request_id": request_id,
                "intent": intent_name,
                "resolved_service": resolved_service_id,
                "response": provider_data,
                "quota": current_quota
            },
            "response_headers": {
                "x-kong-proxy-latency": "1",
                "x-kong-upstream-latency": str(elapsed_ms),
                "x-ai-debug": f"intent={intent_name} service={resolved_service_id} model={service.model_name}",
            },
        }

