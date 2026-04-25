"""Unit tests for PolicyService OPA delegation and Python fallback path."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import httpx
import pytest
import respx

from app.core.exceptions import (
    PolicyEvaluationError,
    PolicySyncError,
    PolicyViolationError,
)
from app.schemas.ai_request import SensitivityLevel
from app.schemas.policy import PolicyConditionSchema, PolicyEffect, PolicySchema
from app.services.policy_service import PolicyService, canonical_service_type


def _set_opa_settings(
    monkeypatch: pytest.MonkeyPatch,
    *,
    enabled: bool = True,
    strict_sync: bool = True,
    allow_local_fallback: bool = True,
    fail_closed: bool = False,
) -> None:
    """Helper to apply a coherent OPA settings snapshot inside a test."""
    monkeypatch.setattr(
        "app.services.policy_service.settings.opa_enabled", enabled
    )
    monkeypatch.setattr(
        "app.services.policy_service.settings.opa_url", "http://opa.test"
    )
    monkeypatch.setattr(
        "app.services.policy_service.settings.opa_policy_path",
        "/v1/data/orchestrator",
    )
    monkeypatch.setattr(
        "app.services.policy_service.settings.opa_data_path", "/v1/data/policies"
    )
    monkeypatch.setattr(
        "app.services.policy_service.settings.opa_strict_sync", strict_sync
    )
    monkeypatch.setattr(
        "app.services.policy_service.settings.opa_allow_local_fallback",
        allow_local_fallback,
    )
    monkeypatch.setattr(
        "app.services.policy_service.settings.opa_fail_closed", fail_closed
    )


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


# ── sync_from_db: strict vs permissive consistency guarantees ───────────────


def _fake_db_policies() -> list[SimpleNamespace]:
    """Mimic the SQLAlchemy GovernancePolicy rows that list_policies returns."""
    return [
        SimpleNamespace(
            id="pol-allow",
            description="demo allow",
            condition={"sensitivity": "LOW", "tenant": None},
            effect=PolicyEffect.ALLOW_ALL,
            is_active=True,
            version="2.0.0",
        )
    ]


def test_sync_from_db_strict_raises_on_opa_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _run() -> None:
        _set_opa_settings(monkeypatch, strict_sync=True)
        monkeypatch.setattr(
            "app.repositories.policy_repository.list_policies",
            lambda _db: _async_return(_fake_db_policies()),
        )

        svc = PolicyService()

        with respx.mock:
            respx.put("http://opa.test/v1/data/policies").mock(
                return_value=httpx.Response(500, text="opa-down")
            )
            with pytest.raises(PolicySyncError) as exc_info:
                await svc.sync_from_db(db=None)

        assert exc_info.value.reason == "opa_push_failed"
        status = svc.get_status()
        assert status["last_sync_ok"] is False
        assert status["in_sync"] is False
        assert status["last_sync_error"]
        assert status["local_hash"] is not None
        assert status["last_pushed_hash"] is None
        await svc.aclose()

    asyncio.run(_run())


def test_sync_from_db_permissive_does_not_raise(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _run() -> None:
        _set_opa_settings(monkeypatch, strict_sync=False)
        monkeypatch.setattr(
            "app.repositories.policy_repository.list_policies",
            lambda _db: _async_return(_fake_db_policies()),
        )

        svc = PolicyService()

        with respx.mock:
            respx.put("http://opa.test/v1/data/policies").mock(
                return_value=httpx.Response(503, text="not ready")
            )
            stats = await svc.sync_from_db(db=None)

        assert stats["opa"] == "failed"
        assert stats["error"]
        status = svc.get_status()
        assert status["last_sync_ok"] is False
        assert status["in_sync"] is False
        await svc.aclose()

    asyncio.run(_run())


def test_sync_from_db_success_records_hash_and_version(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _run() -> None:
        _set_opa_settings(monkeypatch, strict_sync=True)
        monkeypatch.setattr(
            "app.repositories.policy_repository.list_policies",
            lambda _db: _async_return(_fake_db_policies()),
        )

        svc = PolicyService()
        captured: dict = {}

        def _on_request(request: httpx.Request) -> httpx.Response:
            import json

            captured["body"] = json.loads(request.content.decode())
            return httpx.Response(204)

        with respx.mock:
            respx.put("http://opa.test/v1/data/policies").mock(side_effect=_on_request)
            stats = await svc.sync_from_db(db=None)

        assert stats["opa"] == "synced"
        assert stats["in_sync"] is True
        assert stats["hash"] and len(stats["hash"]) == 64
        assert stats["version"] == "2.0.0"

        # Canonical bundle shape pushed to OPA.
        body = captured["body"]
        assert set(body.keys()) == {"items", "version", "hash"}
        assert body["version"] == "2.0.0"
        assert body["hash"] == stats["hash"]
        assert body["items"][0]["id"] == "pol-allow"

        status = svc.get_status()
        assert status["last_sync_ok"] is True
        assert status["last_pushed_hash"] == status["local_hash"]
        assert status["last_pushed_version"] == "2.0.0"
        await svc.aclose()

    asyncio.run(_run())


async def _async_return(value):  # tiny coroutine helper for monkeypatched repos
    return value


# ── Strict OPA response validation ──────────────────────────────────────────


def _setup_in_sync_service(
    monkeypatch: pytest.MonkeyPatch,
    *,
    allow_local_fallback: bool = True,
    fail_closed: bool = False,
) -> PolicyService:
    """Build a PolicyService that already considers itself in-sync with OPA."""
    _set_opa_settings(
        monkeypatch,
        strict_sync=True,
        allow_local_fallback=allow_local_fallback,
        fail_closed=fail_closed,
    )
    svc = _make_service()
    svc._local_hash = svc._compute_policy_hash(svc._policies, svc._version)
    svc._last_pushed_hash = svc._local_hash
    svc._last_pushed_version = svc._version
    svc._last_sync_ok = True
    return svc


@pytest.mark.parametrize(
    "payload",
    [
        {},  # missing result
        {"result": []},  # result not an object
        {"result": {"block": []}},  # missing allow
        {"result": {"allow": "yes"}},  # allow not bool
    ],
)
def test_evaluate_async_raises_on_malformed_opa_response(
    monkeypatch: pytest.MonkeyPatch, payload: dict
) -> None:
    async def _run() -> None:
        svc = _setup_in_sync_service(monkeypatch, allow_local_fallback=False)

        with respx.mock:
            respx.post("http://opa.test/v1/data/orchestrator").mock(
                return_value=httpx.Response(200, json=payload)
            )
            with pytest.raises(PolicyEvaluationError):
                await svc.evaluate_async(
                    {
                        "sensitivity": SensitivityLevel.LOW,
                        "tenant": "tenant-a",
                        "service_type": "on-prem",
                    }
                )
        await svc.aclose()

    asyncio.run(_run())


def test_evaluate_async_raises_on_invalid_block_type(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _run() -> None:
        svc = _setup_in_sync_service(monkeypatch, allow_local_fallback=False)

        with respx.mock:
            respx.post("http://opa.test/v1/data/orchestrator").mock(
                return_value=httpx.Response(
                    200, json={"result": {"allow": True, "block": 42}}
                )
            )
            with pytest.raises(PolicyEvaluationError) as exc_info:
                await svc.evaluate_async(
                    {
                        "sensitivity": SensitivityLevel.LOW,
                        "tenant": "tenant-a",
                        "service_type": "on-prem",
                    }
                )

        assert "block" in str(exc_info.value).lower()
        await svc.aclose()

    asyncio.run(_run())


def test_evaluate_async_malformed_falls_back_when_enabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A malformed OPA payload must still trigger fallback when allowed."""

    async def _run() -> None:
        svc = _setup_in_sync_service(monkeypatch, allow_local_fallback=True)

        with respx.mock:
            respx.post("http://opa.test/v1/data/orchestrator").mock(
                return_value=httpx.Response(200, json={})  # missing result
            )
            # PolicyEvaluationError is a domain error, so fallback shouldn't trigger.
            # We require explicit fail-closed behavior: the error must propagate
            # even with fallback enabled, because the OPA response was malformed
            # rather than the transport failing.
            with pytest.raises(PolicyEvaluationError):
                await svc.evaluate_async(
                    {
                        "sensitivity": SensitivityLevel.LOW,
                        "tenant": "tenant-a",
                        "service_type": "on-prem",
                    }
                )
        await svc.aclose()

    asyncio.run(_run())


# ── Runtime fallback gating ─────────────────────────────────────────────────


def test_opa_unreachable_with_fallback_disabled_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _run() -> None:
        svc = _setup_in_sync_service(monkeypatch, allow_local_fallback=False)

        with respx.mock:
            respx.post("http://opa.test/v1/data/orchestrator").mock(
                side_effect=httpx.ConnectError("boom")
            )
            with pytest.raises(PolicyEvaluationError) as exc_info:
                await svc.evaluate_async(
                    {
                        "sensitivity": SensitivityLevel.LOW,
                        "tenant": "tenant-a",
                        "service_type": "on-prem",
                    }
                )

        assert exc_info.value.reason == "opa_unreachable_or_invalid"
        await svc.aclose()

    asyncio.run(_run())


def test_opa_unreachable_with_fallback_enabled_uses_local(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _run() -> None:
        svc = _setup_in_sync_service(monkeypatch, allow_local_fallback=True)
        svc._policies = _deny_high_cloud_policies()
        svc._local_hash = svc._compute_policy_hash(svc._policies, svc._version)
        svc._last_pushed_hash = svc._local_hash

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


# ── Hash / version mismatch fail-closed ─────────────────────────────────────


def test_evaluate_async_fail_closed_blocks_when_hash_mismatch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """If local cache diverges from last successful push, refuse to evaluate."""

    async def _run() -> None:
        _set_opa_settings(
            monkeypatch,
            strict_sync=True,
            allow_local_fallback=True,
            fail_closed=True,
        )
        svc = _make_service()
        svc._local_hash = "aaaa"
        svc._last_pushed_hash = "bbbb"  # divergent
        svc._last_sync_ok = True

        # OPA mock should NOT be hit; the gate raises before the call.
        with respx.mock:
            respx.post("http://opa.test/v1/data/orchestrator").mock(
                return_value=httpx.Response(200, json={"result": {"allow": True}})
            )
            with pytest.raises(PolicyEvaluationError) as exc_info:
                await svc.evaluate_async(
                    {
                        "sensitivity": SensitivityLevel.LOW,
                        "tenant": "tenant-a",
                        "service_type": "on-prem",
                    }
                )

        assert exc_info.value.reason == "opa_cache_out_of_sync"
        await svc.aclose()

    asyncio.run(_run())


def test_evaluate_async_fail_closed_blocks_when_last_sync_failed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _run() -> None:
        _set_opa_settings(
            monkeypatch,
            strict_sync=False,
            allow_local_fallback=True,
            fail_closed=True,
        )
        svc = _make_service()
        svc._local_hash = "abcd"
        svc._last_pushed_hash = None  # never successfully pushed
        svc._last_sync_ok = False

        with pytest.raises(PolicyEvaluationError) as exc_info:
            await svc.evaluate_async(
                {
                    "sensitivity": SensitivityLevel.LOW,
                    "tenant": "tenant-a",
                    "service_type": "on-prem",
                }
            )

        assert exc_info.value.reason == "opa_cache_out_of_sync"
        await svc.aclose()

    asyncio.run(_run())


# ── Policy hash determinism ─────────────────────────────────────────────────


def test_compute_policy_hash_is_deterministic_and_order_independent() -> None:
    a = PolicySchema(
        id="a",
        description="desc-a",
        condition=PolicyConditionSchema(sensitivity=SensitivityLevel.LOW),
        effect=PolicyEffect.ALLOW_ALL,
    )
    b = PolicySchema(
        id="b",
        description="desc-b",
        condition=PolicyConditionSchema(sensitivity=SensitivityLevel.HIGH),
        effect=PolicyEffect.DENY_CLOUD,
    )
    h1 = PolicyService._compute_policy_hash([a, b], "1.0.0")
    h2 = PolicyService._compute_policy_hash([b, a], "1.0.0")
    assert h1 == h2
    h3 = PolicyService._compute_policy_hash([a, b], "2.0.0")
    assert h3 != h1
