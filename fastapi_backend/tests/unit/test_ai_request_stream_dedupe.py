# fastapi_backend/tests/unit/test_ai_request_stream_dedupe.py
"""Regression tests for AIRequestService.submit_stream.

Guards against the double-emit bug where each streamed token was yielded twice,
producing scrambled/duplicated output in the frontend (e.g. "Hello Hello world").
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from typing import Any, AsyncIterator, Dict, List

import pytest

from app.schemas.ai_request import SensitivityLevel
from app.services import ai_request_service as ars
from app.services.ai_request_service import AIRequestService, _PreFlightResult
from app.services.output_guard_service import OutputGuardService


# ── Test doubles ────────────────────────────────────────────────────────────

class _QuotaStub:
    async def check_quota(self, *_: Any, **__: Any) -> bool:
        return True

    async def increment_usage(self, *_: Any, **__: Any) -> None:
        return None

    async def get_quota_status(self, *_: Any, **__: Any) -> Dict[str, Any]:
        return {"used": 0, "limit": 100, "remaining": 100}


@dataclass
class _FakeAIService:
    model_name: str = "llama3"
    provider_url: str = "http://local/api/chat"
    provider_type: str = "ollama"
    service_type: str = "on-prem"


class _NoopSession:
    async def __aenter__(self) -> "_NoopSession":
        return self

    async def __aexit__(self, *_: Any) -> None:
        return None

    async def execute(self, *_: Any, **__: Any) -> None:
        return None


def _make_service() -> AIRequestService:
    """Build an AIRequestService instance with minimal real collaborators."""
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
        intent_name="general_chat",
        resolved_service_id="ollama-llama3",
        service=_FakeAIService(),
        final_sensitivity=SensitivityLevel.LOW,
        detected_pii_types=[],
        pii_count=0,
        messages=[{"role": "user", "content": "hi"}],
    )


async def _fake_stream(chunks: List[Dict[str, Any]]) -> AsyncIterator[Dict[str, Any]]:
    for chunk in chunks:
        yield chunk


def _patch_ollama(
    monkeypatch: pytest.MonkeyPatch, chunks: List[Dict[str, Any]]
) -> None:
    async def _chat(**_: Any) -> AsyncIterator[Dict[str, Any]]:
        return _fake_stream(chunks)

    monkeypatch.setattr(ars, "ollama_chat", _chat)


def _patch_service(service: AIRequestService, pf: _PreFlightResult) -> None:
    async def _pre_flight(**_: Any) -> _PreFlightResult:
        return pf

    async def _noop_status(**_: Any) -> None:
        return None

    service._run_pre_flight = _pre_flight  # type: ignore[assignment]
    service._update_status_in_new_session = _noop_status  # type: ignore[assignment]


def _collect_tokens(events: List[str]) -> List[str]:
    """Extract non-empty `token` values from SSE data: ... frames, in order."""
    tokens: List[str] = []
    for event in events:
        for line in event.split("\n"):
            if not line.startswith("data: "):
                continue
            payload = json.loads(line[len("data: "):])
            token = payload.get("token")
            if token:
                tokens.append(token)
    return tokens


async def _consume(service: AIRequestService) -> List[str]:
    result = await service.submit_stream(
        db=None,
        current_user={"tenant_id": "tenant-a"},
        body=None,
        nlp=None,
    )
    events: List[str] = []
    async for frame in result["stream"]:
        events.append(frame)
    return events


# ── Tests ───────────────────────────────────────────────────────────────────

def test_submit_stream_concat_equals_source_text(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Concatenation of every emitted token must equal the source text exactly.

    This fails if any token is duplicated (old bug) or dropped.
    """
    source_tokens = [
        "This is a reasonably long streaming chunk number one. ",
        "And here is chunk number two with more text. ",
        "Finally the third chunk terminating the response.",
    ]
    expected = "".join(source_tokens)

    chunks: List[Dict[str, Any]] = [
        {"token": t, "done": False} for t in source_tokens
    ]
    chunks.append({"token": "", "done": True, "usage": {}})

    _patch_ollama(monkeypatch, chunks)
    service = _make_service()
    _patch_service(service, _pre_flight_result())

    events = asyncio.run(_consume(service))
    emitted = "".join(_collect_tokens(events))

    assert emitted == expected, (
        f"Expected emitted text to equal source exactly.\n"
        f"Source : {expected!r}\n"
        f"Emitted: {emitted!r}"
    )


def test_submit_stream_no_duplicate_chunk_prefix(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A single source chunk larger than the redaction carry window must not appear twice.

    Old behavior emitted the safe redacted fragment AND the raw token for the same chunk.
    """
    big_token = "X" * 200  # well above CARRY_SIZE (30)
    chunks: List[Dict[str, Any]] = [
        {"token": big_token, "done": False},
        {"token": "", "done": True, "usage": {}},
    ]

    _patch_ollama(monkeypatch, chunks)
    service = _make_service()
    _patch_service(service, _pre_flight_result())

    events = asyncio.run(_consume(service))
    emitted = "".join(_collect_tokens(events))

    assert len(emitted) == len(big_token), (
        f"Emitted text length {len(emitted)} differs from source {len(big_token)}; "
        "possible duplicate emission."
    )
    assert emitted == big_token


def test_submit_stream_final_event_is_done(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Final SSE frame must carry done=true and completion metadata."""
    chunks: List[Dict[str, Any]] = [
        {"token": "hello world", "done": False},
        {"token": "", "done": True, "usage": {}},
    ]

    _patch_ollama(monkeypatch, chunks)
    service = _make_service()
    _patch_service(service, _pre_flight_result())

    events = asyncio.run(_consume(service))
    assert events, "stream produced no frames"

    last_data_lines = [ln for ln in events[-1].split("\n") if ln.startswith("data: ")]
    assert last_data_lines, "last SSE frame had no data: line"
    last_payload = json.loads(last_data_lines[-1][len("data: "):])

    assert last_payload.get("done") is True
    assert last_payload.get("request_id") == "req-test-1"
    assert last_payload.get("intent") == "general_chat"
