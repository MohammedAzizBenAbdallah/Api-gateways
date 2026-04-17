# app/api/ai.py
"""AI endpoints for submitting an intent-based AI request."""

from __future__ import annotations

import logging
from typing import Any, AsyncIterator, Dict

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_ai_request_service
from app.core.exceptions import (
    IntentNotFoundError,
    ProviderError,
    ServiceNotFoundError,
    TenantIdMissingError,
    TenantNotAuthorizedError,
    PolicyViolationError,
    QuotaExceededError,
    SecurityViolationError,
)
from app.core.middleware import verify_kong_header
from app.core.security import get_current_user
from app.infrastructure.db.session import get_db, get_db_with_user
from app.infrastructure.ai_provider.ollama_client import chat as ollama_chat  # noqa: F401
from app.infrastructure.nlp.spacy_loader import get_nlp
from app.schemas.ai_request import AIRequestSchema
from app.services.ai_request_service import AIRequestService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ai", tags=["AI"])


@router.post("/request", dependencies=[Depends(verify_kong_header)])
async def submit_ai_request(
    body: AIRequestSchema,
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db_with_user),
    current_user: Dict[str, Any] = Depends(get_current_user),
    nlp: Any = Depends(get_nlp),
    ai_request_service: AIRequestService = Depends(get_ai_request_service),
) -> Any:
    """Submit an intent-based AI request (SSE streaming or JSON fallback)."""

    wants_stream = "text/event-stream" in request.headers.get("Accept", "")

    try:
        if wants_stream:
            result = await ai_request_service.submit_stream(
                db=db,
                current_user=current_user,
                body=body,
                nlp=nlp,
            )
            request_id = result["request_id"]
            stream: AsyncIterator[str] = result["stream"]
            return StreamingResponse(
                stream,
                media_type="text/event-stream",
                headers={
                    "Cache-Control": "no-cache",
                    "X-Accel-Buffering": "no",
                    "Connection": "keep-alive",
                    "X-Request-ID": request_id,
                },
            )

        result = await ai_request_service.submit_json(
            db=db,
            current_user=current_user,
            body=body,
            nlp=nlp,
        )

        for k, v in result.get("response_headers", {}).items():
            response.headers[k] = str(v)

        return result.get("data")
    except IntentNotFoundError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except ServiceNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except TenantIdMissingError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    except TenantNotAuthorizedError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except PolicyViolationError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except SecurityViolationError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except QuotaExceededError as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc
    except ProviderError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

