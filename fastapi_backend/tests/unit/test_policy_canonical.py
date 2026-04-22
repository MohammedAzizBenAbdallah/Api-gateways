"""Policy evaluation uses canonical service_type (cloud vs on-prem) for OPA and Python paths."""

from __future__ import annotations

import asyncio
import json

import httpx
import pytest
import respx

from app.core.exceptions import PolicyViolationError
from app.schemas.ai_request import SensitivityLevel
from app.schemas.policy import PolicyConditionSchema, PolicyEffect, PolicySchema
from app.services.policy_service import PolicyService, canonical_service_type


def test_canonical_service_type_cloud_variants() -> None:
    assert canonical_service_type("CLOUD") == "cloud"
    assert canonical_service_type("Cloud") == "cloud"
    assert canonical_service_type("on-prem") == "on-prem"
    assert canonical_service_type("ON-PREM") == "on-prem"
    assert canonical_service_type("on_prem") == "on-prem"


@pytest.mark.parametrize("raw", ["CLOUD", "cloud", "Saas"])
def test_python_path_high_sensitivity_deny_cloud_blocks(
    monkeypatch: pytest.MonkeyPatch, raw: str
) -> None:
    async def _run() -> None:
        monkeypatch.setattr("app.services.policy_service.settings.opa_enabled", False)

        svc = PolicyService()
        svc._policies = [
            PolicySchema(
                id="block-high-cloud",
                description="no high in cloud",
                condition=PolicyConditionSchema(sensitivity=SensitivityLevel.HIGH),
                effect=PolicyEffect.DENY_CLOUD,
            )
        ]
        with pytest.raises(PolicyViolationError) as ei:
            await svc.evaluate_async(
                {
                    "sensitivity": SensitivityLevel.HIGH,
                    "tenant": "tenant-a",
                    "service_type": raw,
                }
            )
        assert ei.value.policy_id == "block-high-cloud"

    asyncio.run(_run())


def test_opa_payload_uses_canonical_service_type(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _run() -> None:
        monkeypatch.setattr("app.services.policy_service.settings.opa_enabled", True)
        monkeypatch.setattr("app.services.policy_service.settings.opa_url", "http://opa.test")

        svc = PolicyService()
        svc._policies = [
            PolicySchema(
                id="p1",
                description="allow",
                condition=PolicyConditionSchema(sensitivity=SensitivityLevel.LOW),
                effect=PolicyEffect.ALLOW_ALL,
            )
        ]
        captured: dict = {}

        def _on_request(request: httpx.Request) -> httpx.Response:
            captured["body"] = json.loads(request.content.decode()) if request.content else {}
            return httpx.Response(200, json={"result": {"allow": True, "block": []}})

        with respx.mock:
            respx.post("http://opa.test/v1/data/orchestrator").mock(side_effect=_on_request)
            await svc.evaluate_async(
                {
                    "sensitivity": SensitivityLevel.LOW,
                    "tenant": "tenant-a",
                    "service_type": "CLOUD",
                }
            )

        assert captured["body"]["input"]["context"]["service_type"] == "cloud"

    asyncio.run(_run())
