# app/services/ai_request_service.py
"""Orchestrate AI request lifecycle including streaming and persistence."""

from __future__ import annotations

import json
import logging
import urllib.parse
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, AsyncIterator, Dict, List, Optional, TYPE_CHECKING

import httpx
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


# ── Shared result container for pre-flight checks ───────────────────────────

@dataclass
class _PreFlightResult:
    """Data collected by the shared pre-flight pipeline."""

    request_id: str
    tenant_id: str
    intent_name: str
    resolved_service_id: str
    service: Any
    final_sensitivity: Any  # SensitivityLevel
    detected_pii_types: List[str]
    pii_count: int
    messages: List[Dict[str, str]]


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

    # ── Private helpers ──────────────────────────────────────────────────────

    def _gemini_headers(self) -> Dict[str, str]:
        """Build Gemini request headers copied from the exploit logic."""
        return {
            "accept": "*/*",
            "content-type": "application/x-www-form-urlencoded;charset=UTF-8",
            "x-same-domain": "1",
            "cookie": "",
        }

    def _build_gemini_payload(self, messages: List[Dict[str, str]]) -> str:
        """Create the same f.req form payload shape used in pythonExploit.py."""
        prompt = "\n".join(
            m.get("content", "").strip()
            for m in messages
            if isinstance(m, dict) and m.get("content")
        ).strip()
        inner = [
            [prompt, 0, None, None, None, None, 0],
            ["en-US"],
            ["", "", "", None, None, None, None, None, None, ""],
            "", "", None, [0], 1, None, None, 1, 0,
            None, None, None, None, None, [[0]], 0,
        ]
        outer = [None, json.dumps(inner)]
        return urllib.parse.urlencode({"f.req": json.dumps(outer)}) + "&"

    def _parse_gemini_response(self, text: str) -> str:
        """Extract response text from wrb.fr lines."""
        cleaned = text.replace(")]}'", "")
        best = ""
        for line in cleaned.splitlines():
            if "wrb.fr" not in line:
                continue
            try:
                data = json.loads(line)
            except Exception:
                continue

            entries: List[List[Any]] = []
            if isinstance(data, list):
                if data and data[0] == "wrb.fr":
                    entries = [data]
                else:
                    entries = [
                        item for item in data
                        if isinstance(item, list) and item and item[0] == "wrb.fr"
                    ]

            for entry in entries:
                try:
                    inner = json.loads(entry[2])
                    if isinstance(inner, list) and len(inner) > 4 and isinstance(inner[4], list):
                        for chunk in inner[4]:
                            if isinstance(chunk, list) and len(chunk) > 1 and isinstance(chunk[1], list):
                                txt = "".join(token for token in chunk[1] if isinstance(token, str))
                                if len(txt) > len(best):
                                    best = txt
                except Exception:
                    continue
        return best.strip()

    async def _call_gemini_json(
        self,
        *,
        provider_url: str,
        messages: List[Dict[str, str]],
    ) -> Dict[str, Any]:
        """Call Gemini endpoint and normalize output into provider_data shape."""
        payload = self._build_gemini_payload(messages)
        headers = self._gemini_headers()
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(provider_url, headers=headers, content=payload)
        if response.status_code != 200:
            raise ProviderError(f"Gemini provider returned HTTP {response.status_code}")

        text = self._parse_gemini_response(response.text)
        if not text:
            raise ProviderError("Gemini provider returned empty/unsupported response format")

        return {
            "message": {"role": "assistant", "content": text},
            "usage": {},
        }

    async def _call_gemini_stream(
        self,
        *,
        provider_url: str,
        messages: List[Dict[str, str]],
    ) -> AsyncIterator[Dict[str, Any]]:
        """Provide a token-like stream contract from Gemini full response."""
        provider_data = await self._call_gemini_json(
            provider_url=provider_url,
            messages=messages,
        )
        text = provider_data.get("message", {}).get("content", "")
        if not text:
            yield {"token": "", "done": True, "usage": {}}
            return

        chunk_size = 48
        for i in range(0, len(text), chunk_size):
            yield {"token": text[i:i + chunk_size], "done": False}
        yield {"token": "", "done": True, "usage": provider_data.get("usage", {})}

    async def _update_status_in_new_session(
        self,
        *,
        request_id: str,
        status: str,
        completed_at: Optional[datetime] = None,
        error_detail: Optional[str] = None,
    ) -> None:
        async with self._session_factory() as session:
            await session.execute(text("SELECT set_config('app.is_admin', 'true', true)"))
            await update_ai_request_status(
                session,
                request_id=request_id,
                status=status,
                completed_at=completed_at,
                error_detail=error_detail,
            )

    async def _run_pre_flight(
        self,
        *,
        db: "AsyncSession",
        current_user: Dict[str, Any],
        body: Any,
        nlp: Any,
    ) -> _PreFlightResult:
        """Shared pre-flight pipeline: auth → quota → record → inspect → policy → security.

        Returns a _PreFlightResult with everything both submit paths need.
        Raises domain exceptions on any check failure.
        """
        request_id = str(uuid.uuid4())
        intent_name: str = body.intent
        environment: str = body.metadata.environment

        # ── Tenant validation ──
        tenant_id = current_user.get("tenant_id")
        if not tenant_id:
            raise TenantIdMissingError()

        # ── Intent resolution ──
        resolved_service_id = self._intent_cache_service.resolve_intent(intent_name)

        # ── Tenant permission check ──
        is_allowed = await check_tenant_service_permission_and_audit(
            db,
            tenant_id=tenant_id,
            service_id=resolved_service_id,
            intent=intent_name,
        )
        if not is_allowed:
            raise TenantNotAuthorizedError(tenant_id=tenant_id, service_id=resolved_service_id)

        # ── Quota check (Redis) ──
        has_quota = await self._quota_service.check_quota(tenant_id)
        if not has_quota:
            logger.warning("Tenant %s exceeded token quota", tenant_id)
            raise QuotaExceededError(tenant_id=tenant_id)

        # ── Service lookup ──
        service = await get_ai_service_by_id(db, service_id=resolved_service_id)
        if service is None:
            raise ServiceNotFoundError(service_id=resolved_service_id)

        # ── Persist tracking record ──
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
            logger.exception("Failed to persist request record: %s", exc)
            raise ProviderError("Failed to persist request record")

        # ── Content inspection (PII detection + sensitivity upgrade) ──
        final_sensitivity, detected_pii_types, pii_count = (
            await self._content_inspector_service.inspect_content(body, nlp)
        )
        if final_sensitivity.value != body.metadata.sensitivity.value:
            logger.warning(
                "Sensitivity upgraded %s → %s for request %s",
                body.metadata.sensitivity.value,
                final_sensitivity.value,
                request_id,
            )

        await update_resolved_sensitivity(
            db,
            request_id=request_id,
            resolved_sensitivity=final_sensitivity.value,
        )

        # ── Policy evaluation ──
        policy_context = {
            "sensitivity": final_sensitivity,
            "tenant": tenant_id,
            "service_type": getattr(service, "service_type", "on-prem"),
        }
        evaluation_results = []
        try:
            evaluation_results = self._policy_service.evaluate(policy_context)
        except PolicyViolationError as exc:
            for res in exc.results:
                await create_policy_audit_log(
                    db,
                    request_id=request_id,
                    policy_id=res.policy_id,
                    effect=res.effect.value,
                    decision=res.decision,
                    context={
                        "sensitivity": final_sensitivity.value,
                        "tenant": tenant_id,
                        "service_type": getattr(service, "service_type", "on-prem"),
                    },
                )
            # Re-raise with PII info for the router/frontend
            raise PolicyViolationError(
                policy_id=exc.policy_id,
                description=exc.description,
                results=exc.results,
                pii_count=pii_count,
                detected_pii_types=detected_pii_types,
            )

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
                    "service_type": getattr(service, "service_type", "on-prem"),
                },
            )

        # ── Build outbound messages ──
        messages: List[Dict[str, str]] = [
            {"role": m.role, "content": m.content} for m in body.payload.messages
        ]

        # ── Prompt security scan (Input Shield) ──
        await self._run_prompt_security_scan(
            request_id=request_id,
            tenant_id=tenant_id,
            messages=messages,
            pii_count=pii_count,
            detected_pii_types=detected_pii_types,
        )

        return _PreFlightResult(
            request_id=request_id,
            tenant_id=tenant_id,
            intent_name=intent_name,
            resolved_service_id=resolved_service_id,
            service=service,
            final_sensitivity=final_sensitivity,
            detected_pii_types=detected_pii_types,
            pii_count=pii_count,
            messages=messages,
        )

    async def _run_prompt_security_scan(
        self,
        *,
        request_id: str,
        tenant_id: str,
        messages: List[Dict[str, str]],
        pii_count: Optional[int] = None,
        detected_pii_types: Optional[List[str]] = None,
    ) -> None:
        """Scan messages for prompt injection and log/block as needed."""
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
                pii_count=pii_count,
                detected_pii_types=detected_pii_types,
            )

        if scan_result.matched_patterns:
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

    # ── Public API ───────────────────────────────────────────────────────────

    async def submit_stream(
        self,
        *,
        db: "AsyncSession",
        current_user: Dict[str, Any],
        body: Any,
        nlp: Any,
    ) -> Dict[str, Any]:
        """Stream SSE events for an AI request."""
        pf = await self._run_pre_flight(
            db=db, current_user=current_user, body=body, nlp=nlp,
        )

        outbound_model = pf.service.model_name
        outbound_provider_url = pf.service.provider_url

        # Capture pre-flight values for the closure
        request_id = pf.request_id
        tenant_id = pf.tenant_id
        intent_name = pf.intent_name
        resolved_service_id = pf.resolved_service_id
        final_sensitivity = pf.final_sensitivity
        detected_pii_types = pf.detected_pii_types
        pii_count = pf.pii_count
        messages = pf.messages

        # ── Initialization Pulse ──
        # Send an immediate empty packet to trigger frontend typing dots.
        # This prevents the UI from "hanging" while waiting for Ollama to load the model.
        async def _event_stream() -> AsyncIterator[str]:
            yield "data: " + json.dumps({"token": "", "done": False}) + "\n\n"
            
            first_token = True
            try:
                if pf.service.provider_type == "gemini":
                    stream_iter = self._call_gemini_stream(
                        provider_url=outbound_provider_url,
                        messages=messages,
                    )
                else:
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
                            
                        # Fetch latest quota status for push
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
                                    "pii_count": pii_count,
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
        pf = await self._run_pre_flight(
            db=db, current_user=current_user, body=body, nlp=nlp,
        )

        outbound_model = pf.service.model_name
        outbound_provider_url = pf.service.provider_url

        try:
            start = datetime.utcnow()
            if pf.service.provider_type == "gemini":
                provider_data = await self._call_gemini_json(
                    provider_url=outbound_provider_url,
                    messages=pf.messages,
                )
            else:
                provider_data = await ollama_chat(
                    provider_url=outbound_provider_url,
                    model=outbound_model if pf.service.provider_type == "ollama" else None,
                    messages=pf.messages,
                    stream=False,
                )
            elapsed_ms = int((datetime.utcnow() - start).total_seconds() * 1000)
        except Exception as exc:
            logger.exception("Provider call failed: %s", exc)
            try:
                await self._update_status_in_new_session(
                    request_id=pf.request_id,
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
                request_id=pf.request_id,
                tenant_id=pf.tenant_id,
                service_id=pf.resolved_service_id,
                model_name=outbound_model,
                input_tokens=prompt_tokens,
                output_tokens=eval_tokens
            )
        
        await self._quota_service.increment_usage(pf.tenant_id, prompt_tokens + eval_tokens)
        
        # Push latest quota status
        current_quota = await self._quota_service.get_quota_status(pf.tenant_id)

        await self._update_status_in_new_session(
            request_id=pf.request_id,
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
                        tenant_id=pf.tenant_id,
                        request_id=pf.request_id,
                        decision="redacted",
                        redacted_types=redaction_result.redacted_types,
                        redaction_count=redaction_result.redaction_count,
                    )

        return {
            "data": {
                "request_id": pf.request_id,
                "intent": pf.intent_name,
                "resolved_service": pf.resolved_service_id,
                "response": provider_data,
                "pii_count": pf.pii_count,
                "detected_pii_types": pf.detected_pii_types,
                "quota": current_quota
            },
            "response_headers": {
                "x-kong-proxy-latency": "1",
                "x-kong-upstream-latency": str(elapsed_ms),
                "x-ai-debug": f"intent={pf.intent_name} service={pf.resolved_service_id} model={pf.service.model_name}",
            },
        }
