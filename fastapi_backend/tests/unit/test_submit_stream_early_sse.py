"""Early SSE thinking pulse and pre-flight error frames."""

from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass
from typing import Any, AsyncIterator, Dict, List

import pytest

from app.core.exceptions import PolicyViolationError
from app.schemas.ai_request import SensitivityLevel
from app.services import ai_request_service as ars
from app.services.ai_request_service import AIRequestService, _PreFlightResult
from app.services.output_guard_service import OutputGuardService


@dataclass
class _FakeAIService:
    model_name: str = "llama3"
    provider_url: str = "http://local/api/chat"
    provider_type: str = "ollama"
    service_type: str = "on-prem"


class _QuotaStub:
    async def check_quota(self, *_: Any, **__: Any) -> bool:
        return True

    async def increment_usage(self, *_: Any, **__: Any) -> None:
        return None

    async def get_quota_status(self, *_: Any, **__: Any) -> Dict[str, Any]:
        return {"used": 0, "limit": 100, "remaining": 100}


class _NoopSession:
    async def __aenter__(self) -> "_NoopSession":
        return self

    async def __aexit__(self, *_: Any) -> None:
        return None

    async def execute(self, *_: Any, **__: Any) -> None:
        return None


def _make_service() -> AIRequestService:
    return AIRequestService(
        intent_cache_service=object(),
        content_inspector_service=object(),
        policy_service=object(),
        quota_service=_QuotaStub(),
        prompt_security_service=object(),
        output_guard_service=OutputGuardService(),
        session_factory=lambda: _NoopSession(),
    )


def _pre_flight_result() -> _PreFlightResult:
    return _PreFlightResult(
        request_id="req-test-1",
        tenant_id="tenant-a",
        provided_intent="auto",
        intent_name="general_chat",
        intent_mode="auto",
        intent_confidence=0.9,
        intent_source="model",
        intent_taxonomy_version="1",
        resolved_service_id="ollama-llama3",
        service=_FakeAIService(),
        final_sensitivity=SensitivityLevel.LOW,
        detected_pii_types=[],
        pii_count=0,
        messages=[{"role": "user", "content": "hi"}],
    )


def _patch_ollama(monkeypatch: pytest.MonkeyPatch, chunks: List[Dict[str, Any]]) -> None:
    async def _fake_stream() -> AsyncIterator[Dict[str, Any]]:
        for chunk in chunks:
            yield chunk

    async def _chat(**_: Any) -> AsyncIterator[Dict[str, Any]]:
        return _fake_stream()

    monkeypatch.setattr(ars, "ollama_chat", _chat)


def _first_payload(events: List[str]) -> Dict[str, Any]:
    for event in events:
        for line in event.split("\n"):
            if line.startswith("data: "):
                return json.loads(line[len("data: ") :])
    raise AssertionError("no SSE payload")


async def _consume_first_n(service: AIRequestService, n: int = 2) -> List[str]:
    result = await service.submit_stream(
        db=None,
        current_user={"tenant_id": "tenant-a"},
        body=None,
        nlp=None,
    )
    events: List[str] = []
    async for frame in result["stream"]:
        events.append(frame)
        if len(events) >= n:
            break
    return events


def test_submit_stream_first_event_is_thinking(monkeypatch: pytest.MonkeyPatch) -> None:
    delay_s = 0.08

    async def _slow_pre_flight(**_: Any) -> _PreFlightResult:
        await asyncio.sleep(delay_s)
        return _pre_flight_result()

    _patch_ollama(
        monkeypatch,
        [{"token": "hi", "done": False}, {"token": "", "done": True}],
    )
    service = _make_service()
    service._run_pre_flight = _slow_pre_flight  # type: ignore[assignment]

    t0 = time.perf_counter()
    events = asyncio.run(_consume_first_n(service, 1))
    elapsed = time.perf_counter() - t0

    assert _first_payload(events).get("status") == "thinking"
    assert elapsed < delay_s * 0.75


def test_submit_stream_preflight_policy_error_sse() -> None:
    async def _raise_policy(**_: Any) -> _PreFlightResult:
        raise PolicyViolationError(
            policy_id="pii-block",
            description="Sensitive data detected",
            results=[],
            pii_count=2,
            detected_pii_types=["EMAIL"],
        )

    service = _make_service()
    service._run_pre_flight = _raise_policy  # type: ignore[assignment]

    events = asyncio.run(_consume_first_n(service, 2))
    assert _first_payload(events).get("status") == "thinking"
    err_payload = json.loads(events[1].split("data: ", 1)[1].strip())
    assert err_payload["error"]["status"] == 403
    assert err_payload["error"]["detail"]["pii_count"] == 2
