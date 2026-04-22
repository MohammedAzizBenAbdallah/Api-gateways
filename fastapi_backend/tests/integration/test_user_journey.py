from __future__ import annotations

from typing import Any, Dict


def _valid_payload() -> Dict[str, Any]:
    return {
        "intent": "general_chat",
        "payload": {"messages": [{"role": "user", "content": "Hello assistant"}]},
        "metadata": {"sensitivity": "LOW", "environment": "dev"},
    }


def test_user_can_submit_json_request_success(app_client: Dict[str, Any]) -> None:
    client = app_client["client"]
    service = app_client["service"]
    service.mode = "success_json"

    resp = client.post("/api/ai/request", json=_valid_payload())

    assert resp.status_code == 200
    data = resp.json()
    assert data["request_id"] == "req-123"
    assert data["resolved_service"] == "ollama_llama3.2"
    assert data["response"]["message"]["content"] == "Hello from AI"
    assert resp.headers["x-kong-proxy-latency"] == "1"


def test_user_can_stream_response(app_client: Dict[str, Any]) -> None:
    client = app_client["client"]
    service = app_client["service"]
    service.mode = "success_stream"

    resp = client.post(
        "/api/ai/request",
        json=_valid_payload(),
        headers={"Accept": "text/event-stream"},
    )

    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/event-stream")
    assert resp.headers["x-request-id"] == "req-stream-1"
    assert '"done":true' in resp.text


def test_request_schema_rejects_unknown_fields(app_client: Dict[str, Any]) -> None:
    client = app_client["client"]
    payload = _valid_payload()
    payload["unexpected"] = "should-fail"

    resp = client.post("/api/ai/request", json=payload)

    assert resp.status_code == 422


def test_policy_violation_returns_structured_403(app_client: Dict[str, Any]) -> None:
    client = app_client["client"]
    service = app_client["service"]
    service.mode = "policy_error"

    resp = client.post("/api/ai/request", json=_valid_payload())

    assert resp.status_code == 403
    detail = resp.json()["detail"]
    assert detail["policy_id"] == "pol-001"
    assert detail["resolved_sensitivity"] == "HIGH"
    assert detail["detected_pii_types"] == ["EMAIL"]


def test_over_quota_request_returns_429(app_client: Dict[str, Any]) -> None:
    client = app_client["client"]
    service = app_client["service"]
    service.mode = "quota_error"

    resp = client.post("/api/ai/request", json=_valid_payload())

    assert resp.status_code == 429
    assert "quota exceeded" in resp.json()["detail"].lower()


def test_prompt_security_violation_returns_403(app_client: Dict[str, Any]) -> None:
    client = app_client["client"]
    service = app_client["service"]
    service.mode = "security_error"

    resp = client.post("/api/ai/request", json=_valid_payload())

    assert resp.status_code == 403
    assert "security violation" in resp.json()["detail"].lower()
