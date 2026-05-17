"""Pre-flight phase A runs classify, inspect, and prompt security in parallel."""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.core.config import settings
from app.schemas.ai_request import SensitivityLevel
from app.services.ai_request_service import AIRequestService
from app.services.output_guard_service import OutputGuardService


@dataclass
class _FakeDecision:
    intent_label: str = "general_chat"
    confidence: float = 0.9
    source: str = "model"
    taxonomy_version: str = "1"


class _FakeMessage:
    role: str = "user"
    content: str = "hello"


class _FakeBody:
    intent: str = settings.intent_auto_token

    def __init__(self) -> None:
        self.payload = MagicMock()
        self.payload.messages = [_FakeMessage()]
        self.metadata = MagicMock()
        self.metadata.environment = "dev"
        self.metadata.sensitivity = SensitivityLevel.LOW


class _QuotaStub:
    async def check_quota(self, *_: Any, **__: Any) -> bool:
        return True

    async def increment_usage(self, *_: Any, **__: Any) -> None:
        return None

    async def get_quota_status(self, *_: Any, **__: Any) -> dict:
        return {}


def test_pre_flight_phase_a_parallel_wall_clock(monkeypatch: pytest.MonkeyPatch) -> None:
    delay = 0.06
    body = _FakeBody()

    intent_cache = MagicMock()
    intent_cache.resolve_intent.return_value = "ollama-llama3"

    classifier = MagicMock()
    classifier.is_configured = True

    async def _slow_classify(**_: Any) -> _FakeDecision:
        await asyncio.sleep(delay)
        return _FakeDecision()

    classifier.classify = _slow_classify

    inspector = MagicMock()

    async def _slow_inspect(*_: Any, **__: Any) -> tuple:
        await asyncio.sleep(delay)
        return (SensitivityLevel.LOW, [], 0)

    inspector.inspect_content = _slow_inspect

    scan_result = MagicMock()
    scan_result.is_blocked = False
    scan_result.matched_patterns = []

    prompt_security = MagicMock()
    prompt_security.scan_messages = AsyncMock(return_value=scan_result)

    policy = MagicMock()
    policy.evaluate_async = AsyncMock(return_value=[])

    import app.services.ai_request_service as ars

    monkeypatch.setattr(
        ars,
        "get_ai_service_by_id",
        AsyncMock(
            return_value=MagicMock(
                model_name="m",
                provider_url="http://x",
                provider_type="ollama",
                service_type="on-prem",
            )
        ),
    )
    monkeypatch.setattr(ars, "create_ai_request", AsyncMock())
    monkeypatch.setattr(ars, "update_resolved_sensitivity", AsyncMock())
    monkeypatch.setattr(ars, "create_policy_audit_log", AsyncMock())
    monkeypatch.setattr(
        ars,
        "check_tenant_service_permission_and_audit",
        AsyncMock(return_value=True),
    )

    service = AIRequestService(
        intent_cache_service=intent_cache,
        content_inspector_service=inspector,
        policy_service=policy,
        quota_service=_QuotaStub(),
        prompt_security_service=prompt_security,
        output_guard_service=OutputGuardService(),
        session_factory=MagicMock(),
        intent_classifier_client=classifier,
    )
    service._messages_to_classify_text = lambda _: "hello"  # type: ignore[method-assign]

    db = MagicMock()
    db.execute = AsyncMock()

    async def _run() -> None:
        nonlocal pf, elapsed
        t0 = time.perf_counter()
        pf = await service._run_pre_flight(
            db=db,
            current_user={"tenant_id": "tenant-a"},
            body=body,
            nlp=None,
        )
        elapsed = time.perf_counter() - t0

    pf = None
    elapsed = 0.0
    asyncio.run(_run())

    assert pf is not None
    assert pf.intent_name == "general_chat"
    assert elapsed < delay * 1.8, f"expected parallel ~{delay}s, got {elapsed:.3f}s"
