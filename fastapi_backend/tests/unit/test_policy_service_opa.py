"""Unit tests for PolicyService OPA delegation and Python fallback path."""

from __future__ import annotations

import asyncio

import httpx
import pytest
import respx

from app.core.exceptions import PolicyViolationError
from app.schemas.ai_request import SensitivityLevel
from app.schemas.policy import PolicyConditionSchema, PolicyEffect, PolicySchema
from app.services.policy_service import PolicyService, canonical_service_type


# ── Fixtures ────────────────────────────────────────────────────────────────


def _allow_policies() -> list[PolicySchema]:
    return [
        PolicySchema(
            id="pol-allow",
            description="demo allow",
            condition=PolicyConditionSchema(sensitivity=SensitivityLevel.LOW),
            effect=PolicyEffect.ALLOW_ALL,
        )
    ]


def _deny_high_cloud_policies() -> list[PolicySchema]:
    return [
        PolicySchema(
            id="block-high-cloud",
            description="no high in cloud",
            condition=PolicyConditionSchema(sensitivity=SensitivityLevel.HIGH),
            effect=PolicyEffect.DENY_CLOUD,
        )
    ]


def _make_service() -> PolicyService:
    svc = PolicyService()
    svc._policies = _allow_policies()
    return svc


# ── canonical_service_type ──────────────────────────────────────────────────


def test_canonical_service_type_normalizes_cloud_variants() -> None:
    assert canonical_service_type("CLOUD") == "cloud"
    assert canonical_service_type("Cloud") == "cloud"
    assert canonical_service_type("SaaS") == "cloud"
    assert canonical_service_type("hosted") == "cloud"


def test_canonical_service_type_normalizes_onprem_variants() -> None:
    assert canonical_service_type("on-prem") == "on-prem"
    assert canonical_service_type("ON-PREM") == "on-prem"
    assert canonical_service_type("on_prem") == "on-prem"
    assert canonical_service_type("self-hosted") == "on-prem"


def test_canonical_service_type_defaults_for_missing() -> None:
    assert canonical_service_type(None) == "on-prem"
    assert canonical_service_type("") == "on-prem"


# ── evaluate_async via OPA (allow / deny) ───────────────────────────────────


def test_evaluate_async_opa_allow(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _run() -> None:
        monkeypatch.setattr(
            "app.services.policy_service.settings.opa_enabled", True
        )
        monkeypatch.setattr(
            "app.services.policy_service.settings.opa_url", "http://opa.test"
        )
        monkeypatch.setattr(
            "app.services.policy_service.settings.opa_policy_path",
            "/v1/data/orchestrator",
        )

        svc = _make_service()

        with respx.mock:
            respx.post("http://opa.test/v1/data/orchestrator").mock(
                return_value=httpx.Response(
                    200, json={"result": {"allow": True, "block": []}}
                )
            )
            results = await svc.evaluate_async(
                {
                    "sensitivity": SensitivityLevel.LOW,
                    "tenant": "tenant-a",
                    "service_type": "on-prem",
                }
            )

        assert results, "expected matching policies to surface as ALLOW results"
        assert all(r.decision == "ALLOW" for r in results)
        await svc.aclose()

    asyncio.run(_run())


def test_evaluate_async_opa_deny_with_block_object(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _run() -> None:
        monkeypatch.setattr(
            "app.services.policy_service.settings.opa_enabled", True
        )
        monkeypatch.setattr(
            "app.services.policy_service.settings.opa_url", "http://opa.test"
        )
        monkeypatch.setattr(
            "app.services.policy_service.settings.opa_policy_path",
            "/v1/data/orchestrator",
        )

        svc = _make_service()

        with respx.mock:
            respx.post("http://opa.test/v1/data/orchestrator").mock(
                return_value=httpx.Response(
                    200,
                    json={"result": {"allow": False, "block": {"pol-allow": True}}},
                )
            )
            with pytest.raises(PolicyViolationError) as exc_info:
                await svc.evaluate_async(
                    {
                        "sensitivity": SensitivityLevel.LOW,
                        "tenant": "tenant-a",
                        "service_type": "on-prem",
                    }
                )

        assert exc_info.value.policy_id == "pol-allow"
        assert any(r.decision == "DENY" for r in exc_info.value.results)
        await svc.aclose()

    asyncio.run(_run())


def test_evaluate_async_opa_deny_with_block_array(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _run() -> None:
        monkeypatch.setattr(
            "app.services.policy_service.settings.opa_enabled", True
        )
        monkeypatch.setattr(
            "app.services.policy_service.settings.opa_url", "http://opa.test"
        )
        monkeypatch.setattr(
            "app.services.policy_service.settings.opa_policy_path",
            "/v1/data/orchestrator",
        )

        svc = _make_service()

        with respx.mock:
            respx.post("http://opa.test/v1/data/orchestrator").mock(
                return_value=httpx.Response(
                    200,
                    json={"result": {"allow": False, "block": ["pol-allow"]}},
                )
            )
            with pytest.raises(PolicyViolationError) as exc_info:
                await svc.evaluate_async(
                    {
                        "sensitivity": SensitivityLevel.LOW,
                        "tenant": "tenant-a",
                        "service_type": "cloud",
                    }
                )

        assert exc_info.value.policy_id == "pol-allow"
        await svc.aclose()

    asyncio.run(_run())


def test_evaluate_async_payload_uses_canonical_service_type(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """OPA always receives canonical 'cloud' / 'on-prem' even with raw inputs."""

    async def _run() -> None:
        monkeypatch.setattr(
            "app.services.policy_service.settings.opa_enabled", True
        )
        monkeypatch.setattr(
            "app.services.policy_service.settings.opa_url", "http://opa.test"
        )
        monkeypatch.setattr(
            "app.services.policy_service.settings.opa_policy_path",
            "/v1/data/orchestrator",
        )

        svc = _make_service()
        captured: dict = {}

        def _on_request(request: httpx.Request) -> httpx.Response:
            import json

            captured["body"] = json.loads(request.content.decode())
            return httpx.Response(200, json={"result": {"allow": True, "block": []}})

        with respx.mock:
            respx.post("http://opa.test/v1/data/orchestrator").mock(
                side_effect=_on_request
            )
            await svc.evaluate_async(
                {
                    "sensitivity": SensitivityLevel.LOW,
                    "tenant": "tenant-a",
                    "service_type": "CLOUD",
                }
            )

        assert captured["body"]["input"]["context"]["service_type"] == "cloud"
        assert captured["body"]["input"]["context"]["sensitivity"] == "LOW"
        await svc.aclose()

    asyncio.run(_run())


# ── evaluate_async fallback to Python when OPA disabled ─────────────────────


@pytest.mark.parametrize("raw_service_type", ["CLOUD", "cloud", "SaaS"])
def test_python_fallback_high_sensitivity_deny_cloud(
    monkeypatch: pytest.MonkeyPatch, raw_service_type: str
) -> None:
    async def _run() -> None:
        monkeypatch.setattr(
            "app.services.policy_service.settings.opa_enabled", False
        )

        svc = PolicyService()
        svc._policies = _deny_high_cloud_policies()

        with pytest.raises(PolicyViolationError) as exc_info:
            await svc.evaluate_async(
                {
                    "sensitivity": SensitivityLevel.HIGH,
                    "tenant": "tenant-a",
                    "service_type": raw_service_type,
                }
            )

        assert exc_info.value.policy_id == "block-high-cloud"

    asyncio.run(_run())


def test_python_fallback_allow_path(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _run() -> None:
        monkeypatch.setattr(
            "app.services.policy_service.settings.opa_enabled", False
        )

        svc = _make_service()
        results = await svc.evaluate_async(
            {
                "sensitivity": SensitivityLevel.LOW,
                "tenant": "tenant-a",
                "service_type": "on-prem",
            }
        )

        assert results
        assert all(r.decision == "ALLOW" for r in results)

    asyncio.run(_run())


# ── OPA unreachable falls back to Python evaluator ──────────────────────────


def test_opa_failure_falls_back_to_python(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _run() -> None:
        monkeypatch.setattr(
            "app.services.policy_service.settings.opa_enabled", True
        )
        monkeypatch.setattr(
            "app.services.policy_service.settings.opa_url", "http://opa.test"
        )
        monkeypatch.setattr(
            "app.services.policy_service.settings.opa_policy_path",
            "/v1/data/orchestrator",
        )

        svc = PolicyService()
        svc._policies = _deny_high_cloud_policies()

        with respx.mock:
            respx.post("http://opa.test/v1/data/orchestrator").mock(
                side_effect=httpx.ConnectError("boom")
            )
            with pytest.raises(PolicyViolationError) as exc_info:
                await svc.evaluate_async(
                    {
                        "sensitivity": SensitivityLevel.HIGH,
                        "tenant": "tenant-a",
                        "service_type": "cloud",
                    }
                )

        assert exc_info.value.policy_id == "block-high-cloud"
        await svc.aclose()

    asyncio.run(_run())


# ── Sync wrapper (legacy) still uses Python evaluator ───────────────────────


def test_sync_evaluate_uses_python_evaluator() -> None:
    svc = _make_service()
    results = svc.evaluate(
        {
            "sensitivity": SensitivityLevel.LOW,
            "tenant": "tenant-a",
            "service_type": "on-prem",
        }
    )
    assert results
    assert all(r.decision == "ALLOW" for r in results)
