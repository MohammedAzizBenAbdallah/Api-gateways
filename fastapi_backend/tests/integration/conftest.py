from __future__ import annotations

from typing import Any, AsyncIterator, Dict

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.ai import router as ai_router
from app.api.dependencies import get_ai_request_service
from app.core.exceptions import (
    PolicyViolationError,
    ProviderError,
    QuotaExceededError,
    SecurityViolationError,
)
from app.core.middleware import verify_kong_header
from app.core.security import get_current_user
from app.infrastructure.db.session import get_db_with_user
from app.infrastructure.nlp.spacy_loader import get_nlp
from app.schemas.policy import PolicyEffect, PolicyEvaluationResult


class FakeAIRequestService:
    """Scenario-driven fake service for API integration tests."""

    def __init__(self) -> None:
        self.mode = "success_json"

    async def submit_json(self, **_: Any) -> Dict[str, Any]:
        if self.mode == "quota_error":
            raise QuotaExceededError(tenant_id="tenant-a")
        if self.mode == "security_error":
            raise SecurityViolationError(
                prompt_hash="abc123",
                matched_patterns=["ignore previous instructions"],
                score=0.95,
            )
        if self.mode == "policy_error":
            result = PolicyEvaluationResult(
                policy_id="pol-001",
                effect=PolicyEffect.DENY_ALL,
                decision="DENY",
                description="High sensitivity blocked for this tenant",
            )
            raise PolicyViolationError(
                policy_id="pol-001",
                description="High sensitivity blocked for this tenant",
                results=[result],
                original_sensitivity="LOW",
                resolved_sensitivity="HIGH",
                detected_pii_types=["EMAIL"],
            )
        if self.mode == "provider_error":
            raise ProviderError("upstream provider unavailable")

        return {
            "data": {
                "request_id": "req-123",
                "intent": "general_chat",
                "resolved_service": "ollama_llama3.2",
                "resolved_sensitivity": "LOW",
                "service_type": "on-prem",
                "response": {"message": {"content": "Hello from AI"}},
                "quota": {"used": 20, "limit": 1000, "remaining": 980},
            },
            "response_headers": {
                "x-kong-proxy-latency": "1",
                "x-kong-upstream-latency": "12",
            },
        }

    async def submit_stream(self, **_: Any) -> Dict[str, Any]:
        if self.mode == "provider_error":
            raise ProviderError("stream provider unavailable")

        async def _stream() -> AsyncIterator[str]:
            yield 'data: {"token":"Hello ","done":false}\n\n'
            yield 'data: {"token":"world","done":true,"request_id":"req-stream-1"}\n\n'

        return {"request_id": "req-stream-1", "stream": _stream()}


@pytest.fixture
def app_client() -> Dict[str, Any]:
    app = FastAPI()
    app.include_router(ai_router, prefix="/api")

    fake_service = FakeAIRequestService()

    app.dependency_overrides[verify_kong_header] = lambda: None
    app.dependency_overrides[get_current_user] = lambda: {
        "sub": "user-1",
        "email": "user@example.com",
        "tenant_id": "tenant-a",
        "realm_access": {"roles": ["user"]},
    }

    async def _fake_db() -> AsyncIterator[None]:
        yield None

    app.dependency_overrides[get_db_with_user] = _fake_db
    app.dependency_overrides[get_nlp] = lambda: object()
    app.dependency_overrides[get_ai_request_service] = lambda: fake_service

    client = TestClient(app)
    return {"client": client, "service": fake_service}
