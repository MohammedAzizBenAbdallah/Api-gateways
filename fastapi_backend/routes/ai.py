import json
import uuid
import httpx
from datetime import datetime
from typing import List, Literal, AsyncGenerator
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from database import get_db, AsyncSessionLocal
from auth import get_current_user
from models import (
    AIService,
    TenantServicePermission,
    PermissionAuditLog,
    IntentRouting,
    AIRequestRecord,
)
from middleware import verify_kong_header

router = APIRouter(prefix="/ai", tags=["AI"])


# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------

class MessageSchema(BaseModel):
    model_config = {"extra": "forbid"}
    role: str
    content: str


class AIRequestPayload(BaseModel):
    model_config = {"extra": "forbid"}
    messages: List[MessageSchema]


class AIRequestMetadata(BaseModel):
    model_config = {"extra": "forbid"}
    sensitivity: Literal["LOW", "HIGH"] = "LOW"
    environment: Literal["dev", "prod"] = "dev"


class AIRequest(BaseModel):
    model_config = {"extra": "forbid"}
    intent: Literal["code_generation", "general_chat", "summarization"]
    payload: AIRequestPayload
    metadata: AIRequestMetadata


# ---------------------------------------------------------------------------
# Auth + permission audit helper (unchanged)
# ---------------------------------------------------------------------------

async def authorize_tenant_service(
    service_id: str,
    user: dict,
    db: AsyncSession,
    intent: str | None = None,
):
    tenant_id = user.get("tenant_id")
    if not tenant_id:
        raise HTTPException(status_code=401, detail="Missing X-Tenant-ID in token claims")

    query = select(TenantServicePermission).where(
        TenantServicePermission.tenant_id == tenant_id,
        TenantServicePermission.service_id == service_id
    )
    result = await db.execute(query)
    permission = result.scalars().first()
    is_allowed = permission is not None and permission.allowed

    audit_log = PermissionAuditLog(
        tenant_id=tenant_id,
        service_id=service_id,
        action="ALLOW" if is_allowed else "DENY",
        performed_by="system",
        reason="Policy check passed" if is_allowed else "Policy check failed",
        intent=intent,
    )
    db.add(audit_log)
    await db.commit()

    if not is_allowed:
        raise HTTPException(
            status_code=403,
            detail=f"Forbidden: Tenant '{tenant_id}' does not have access to service '{service_id}'"
        )
    return True


# ---------------------------------------------------------------------------
# Tracking helpers — each opens and closes its own short-lived session
# ---------------------------------------------------------------------------

async def _update_request_status(
    request_id: str,
    status: str,
    completed_at: datetime | None = None,
    error_detail: str | None = None,
):
    """Update ai_requests row using an independent session (safe inside generator)."""
    values: dict = {"status": status}
    if completed_at is not None:
        values["completed_at"] = completed_at
    if error_detail is not None:
        values["error_detail"] = error_detail

    try:
        async with AsyncSessionLocal() as db:
            await db.execute(
                update(AIRequestRecord)
                .where(AIRequestRecord.request_id == request_id)
                .values(**values)
            )
            await db.commit()
    except Exception as exc:
        # Never let a tracking failure crash the stream
        print(f"[tracking] Failed to update request {request_id} → {status}: {exc}")


# ---------------------------------------------------------------------------
# SSE async generator
# ---------------------------------------------------------------------------

async def _sse_generator(
    provider_url: str,
    outbound_body: dict,
    request_id: str,
    intent: str,
    resolved_service_id: str,
) -> AsyncGenerator[str, None]:
    """
    Streams Ollama NDJSON as Server-Sent Events and tracks lifecycle in ai_requests.

    SSE event formats:
      data: {"token": "...", "done": false}\\n\\n
      data: {"token": "", "done": true, "request_id": "...",
             "resolved_service": "...", "intent": "..."}\\n\\n
      data: {"error": "...", "done": true}\\n\\n
    """
    first_token = True

    async with httpx.AsyncClient() as client:
        try:
            async with client.stream(
                "POST",
                provider_url,
                json=outbound_body,
                timeout=None,
            ) as r:
                async for line in r.aiter_lines():
                    if not line.strip():
                        continue
                    try:
                        chunk = json.loads(line)
                    except json.JSONDecodeError:
                        continue

                    token = chunk.get("message", {}).get("content", "")
                    done = chunk.get("done", False)

                    if done:
                        # Final SSE event
                        yield (
                            f"data: {json.dumps({'token': '', 'done': True, 'request_id': request_id, 'resolved_service': resolved_service_id, 'intent': intent})}\n\n"
                        )
                        # Update tracking: completed
                        await _update_request_status(
                            request_id, "completed", completed_at=datetime.utcnow()
                        )
                        return

                    elif token:
                        if first_token:
                            first_token = False
                            # Update tracking: streaming (first token received)
                            await _update_request_status(request_id, "streaming")
                        yield f"data: {json.dumps({'token': token, 'done': False})}\n\n"

        except Exception as e:
            print(f"[SSE] Stream error: {e}")
            yield f"data: {json.dumps({'error': f'Stream interrupted: {str(e)}', 'done': True})}\n\n"
            # Update tracking: failed
            await _update_request_status(
                request_id, "failed",
                completed_at=datetime.utcnow(),
                error_detail=str(e),
            )


# ---------------------------------------------------------------------------
# POST /ai/request  — unified intent-based endpoint
#   • Accept: text/event-stream  → SSE streaming response
#   • Accept: application/json   → full JSON (curl/testing fallback)
# ---------------------------------------------------------------------------

@router.post("/request", dependencies=[Depends(verify_kong_header)])
async def ai_request(
    body: AIRequest,
    request: Request,
    response: Response,
    user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    wants_stream = "text/event-stream" in request.headers.get("Accept", "")

    # 1. Generate request ID immediately
    request_id = str(uuid.uuid4())

    # 2. Resolve intent → service_id
    intent_result = await db.execute(
        select(IntentRouting).where(IntentRouting.intent == body.intent)
    )
    routing_row = intent_result.scalars().first()
    if not routing_row:
        raise HTTPException(
            status_code=422,
            detail=f"Unknown intent: '{body.intent}'. No routing rule found."
        )
    resolved_service_id = routing_row.service_id

    # 3. Tenant permission check + audit log
    await authorize_tenant_service(resolved_service_id, user, db, intent=body.intent)

    # 4. Fetch service record
    svc_result = await db.execute(
        select(AIService).where(AIService.service_id == resolved_service_id)
    )
    service = svc_result.scalars().first()
    if not service:
        raise HTTPException(
            status_code=404,
            detail=f"Resolved service '{resolved_service_id}' not found in ai_services."
        )

    # 5. Write ai_requests record immediately (status=received)
    #    Fail fast — do not proceed if tracking record cannot be persisted.
    try:
        ai_record = AIRequestRecord(
            request_id=request_id,
            tenant_id=user.get("tenant_id"),
            intent=body.intent,
            resolved_service_id=resolved_service_id,
            sensitivity=body.metadata.sensitivity,
            environment=body.metadata.environment,
            status="received",
            started_at=datetime.utcnow(),
        )
        db.add(ai_record)
        await db.commit()
    except Exception as e:
        print(f"[tracking] Failed to write received record: {e}")
        raise HTTPException(
            status_code=500,
            detail="Failed to persist request record. Request aborted."
        )

    print(
        f"[/ai/request] id={request_id} intent={body.intent} "
        f"→ {resolved_service_id} model={service.model_name} stream={wants_stream}"
    )

    # 6. Build messages list
    messages = [{"role": m.role, "content": m.content} for m in body.payload.messages]

    # ── SSE STREAMING PATH ────────────────────────────────────────────────
    if wants_stream:
        outbound_body = {
            "model": service.model_name,
            "messages": messages,
            "stream": True,
        }
        return StreamingResponse(
            _sse_generator(
                provider_url=service.provider_url,
                outbound_body=outbound_body,
                request_id=request_id,
                intent=body.intent,
                resolved_service_id=resolved_service_id,
            ),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",
                "Connection": "keep-alive",
                "X-Request-ID": request_id,
            },
        )

    # ── JSON FALLBACK PATH ────────────────────────────────────────────────
    if service.provider_type == "ollama":
        outbound_body = {
            "model": service.model_name,
            "messages": messages,
            "stream": False,
        }
    else:
        outbound_body = {"messages": messages}

    async with httpx.AsyncClient() as client:
        try:
            prov_resp = await client.post(
                service.provider_url,
                json=outbound_body,
                timeout=120.0,
            )
            provider_data = prov_resp.json()

            # Update tracking: completed
            await db.execute(
                update(AIRequestRecord)
                .where(AIRequestRecord.request_id == request_id)
                .values(status="completed", completed_at=datetime.utcnow())
            )
            await db.commit()

            response.headers["x-kong-proxy-latency"] = "1"
            response.headers["x-kong-upstream-latency"] = str(
                int(prov_resp.elapsed.total_seconds() * 1000)
            )
            response.headers["x-ai-debug"] = (
                f"intent={body.intent} service={resolved_service_id} model={service.model_name}"
            )

            return {
                "request_id": request_id,
                "intent": body.intent,
                "resolved_service": resolved_service_id,
                "response": provider_data,
            }

        except Exception as e:
            print(f"[/ai/request JSON] Provider error: {e}")
            # Update tracking: failed
            try:
                await db.execute(
                    update(AIRequestRecord)
                    .where(AIRequestRecord.request_id == request_id)
                    .values(
                        status="failed",
                        completed_at=datetime.utcnow(),
                        error_detail=str(e),
                    )
                )
                await db.commit()
            except Exception as track_exc:
                print(f"[tracking] Failed to write failed status: {track_exc}")
            raise HTTPException(
                status_code=500,
                detail=f"Failed to connect to AI provider: {str(e)}"
            )
