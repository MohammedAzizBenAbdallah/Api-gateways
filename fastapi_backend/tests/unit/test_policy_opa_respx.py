"""OPA delegation on PolicyService with mocked HTTP (ORK-028 / ORK-049)."""

from __future__ import annotations

import asyncio

import httpx
import pytest
import respx

from app.core.exceptions import PolicyViolationError
from app.schemas.ai_request import SensitivityLevel
from app.schemas.policy import PolicyConditionSchema, PolicyEffect, PolicySchema
from app.services.policy_service import PolicyService


def _policies() -> list[PolicySchema]:
    return [
        PolicySchema(
            id="pol-demo",
            description="demo allow",
            condition=PolicyConditionSchema(sensitivity=SensitivityLevel.LOW),
            effect=PolicyEffect.ALLOW_ALL,
        )
    ]


def test_evaluate_async_opa_allow(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _run() -> None:
        monkeypatch.setattr("app.services.policy_service.settings.opa_enabled", True)
        monkeypatch.setattr("app.services.policy_service.settings.opa_url", "http://opa.test")

        svc = PolicyService()
        svc._policies = _policies()

        with respx.mock:
            respx.post("http://opa.test/v1/data/orchestrator").mock(
                return_value=httpx.Response(200, json={"result": {"allow": True, "block": {}}})
            )
            ctx = {
                "sensitivity": SensitivityLevel.LOW,
                "tenant": "tenant-a",
                "service_type": "on-prem",
            }
            out = await svc.evaluate_async(ctx)

        assert out
        assert all(r.decision == "ALLOW" for r in out)

    asyncio.run(_run())


def test_evaluate_async_opa_deny(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _run() -> None:
        monkeypatch.setattr("app.services.policy_service.settings.opa_enabled", True)
        monkeypatch.setattr("app.services.policy_service.settings.opa_url", "http://opa.test")

        svc = PolicyService()
        svc._policies = _policies()

        with respx.mock:
            respx.post("http://opa.test/v1/data/orchestrator").mock(
                return_value=httpx.Response(
                    200,
                    json={"result": {"allow": False, "block": {"pol-demo": True}}},
                )
            )
            ctx = {
                "sensitivity": SensitivityLevel.LOW,
                "tenant": "tenant-a",
                "service_type": "on-prem",
            }
            with pytest.raises(PolicyViolationError) as ei:
                await svc.evaluate_async(ctx)
        assert ei.value.policy_id == "pol-demo"

    asyncio.run(_run())


def test_evaluate_async_opa_deny_block_json_array(monkeypatch: pytest.MonkeyPatch) -> None:
    """Real OPA serializes partial set rules as JSON arrays, not dicts."""

    async def _run() -> None:
        monkeypatch.setattr("app.services.policy_service.settings.opa_enabled", True)
        monkeypatch.setattr("app.services.policy_service.settings.opa_url", "http://opa.test")

        svc = PolicyService()
        svc._policies = _policies()

        with respx.mock:
            respx.post("http://opa.test/v1/data/orchestrator").mock(
                return_value=httpx.Response(
                    200,
                    json={"result": {"allow": False, "block": ["pol-demo"]}},
                )
            )
            ctx = {
                "sensitivity": SensitivityLevel.LOW,
                "tenant": "tenant-a",
                "service_type": "on-prem",
            }
            with pytest.raises(PolicyViolationError) as ei:
                await svc.evaluate_async(ctx)
        assert ei.value.policy_id == "pol-demo"

    asyncio.run(_run())
