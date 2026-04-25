# app/services/policy_service.py
"""Service for loading and evaluating governance policies via OPA.

Evaluation is delegated to an external Open Policy Agent (OPA) instance over
HTTP. A pure-Python evaluator is kept as a rollback path behind the
`OPA_ENABLED` feature flag so the service degrades gracefully if OPA is
unreachable or temporarily disabled.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, List, Optional, TYPE_CHECKING

import httpx

from app.core.config import settings
from app.schemas.policy import (
    PolicyEffect,
    PolicyEvaluationResult,
    PolicySchema,
)

if TYPE_CHECKING:  # pragma: no cover
    from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


_CLOUD_ALIASES = {"cloud", "saas", "managed", "hosted"}
_ONPREM_ALIASES = {"on-prem", "onprem", "on_prem", "on premises", "self-hosted"}


def canonical_service_type(value: Any) -> str:
    """Normalize free-form service_type strings into canonical OPA values."""
    if value is None:
        return "on-prem"
    raw = str(value).strip().lower().replace(" ", "-").replace("_", "-")
    if raw in _CLOUD_ALIASES or raw == "cloud":
        return "cloud"
    if raw in _ONPREM_ALIASES or raw == "on-prem":
        return "on-prem"
    return raw or "on-prem"


def _coerce_sensitivity(value: Any) -> Optional[str]:
    """Render a sensitivity context value as a plain string for OPA."""
    if value is None:
        return None
    inner = getattr(value, "value", value)
    return str(inner)


class PolicyService:
    """Loads policy data from the platform DB and delegates evaluation to OPA."""

    def __init__(self) -> None:
        self._policies: List[PolicySchema] = []
        self._version: str = "1.0.0"
        self._http_client: Optional[httpx.AsyncClient] = None

    @property
    def policies(self) -> List[PolicySchema]:
        return self._policies

    @property
    def version(self) -> str:
        return self._version

    # ── Lifecycle helpers ────────────────────────────────────────────────────

    def _get_client(self) -> httpx.AsyncClient:
        if self._http_client is None:
            self._http_client = httpx.AsyncClient(
                base_url=settings.opa_url,
                timeout=settings.opa_timeout_seconds,
            )
        return self._http_client

    async def aclose(self) -> None:
        if self._http_client is not None:
            await self._http_client.aclose()
            self._http_client = None

    # ── Policy data sync ─────────────────────────────────────────────────────

    async def sync_from_db(self, db: "AsyncSession") -> dict:
        """Refresh the in-memory cache from DB and push it to OPA data API."""
        from app.repositories.policy_repository import list_policies

        logger.info("[PolicyService] Syncing policies from database...")
        db_policies = await list_policies(db)

        new_policies: List[PolicySchema] = []
        for p in db_policies:
            if not p.is_active:
                continue
            try:
                new_policies.append(
                    PolicySchema(
                        id=p.id,
                        description=p.description,
                        condition=p.condition,
                        effect=p.effect,
                    )
                )
            except Exception as e:
                logger.error("Failed to parse policy %s from DB: %s", p.id, str(e))

        self._policies = new_policies
        if db_policies:
            self._version = db_policies[0].version

        opa_status = "disabled"
        if settings.opa_enabled:
            opa_status = await self._push_policies_to_opa()

        logger.info(
            "Successfully synced %d active policies (opa=%s).",
            len(self._policies),
            opa_status,
        )
        return {
            "total_in_db": len(db_policies),
            "active_synced": len(self._policies),
            "version": self._version,
            "opa": opa_status,
        }

    async def _push_policies_to_opa(self) -> str:
        """Push the active policy set as an OPA data document.

        Returns a status string ("synced", "skipped", "failed") for diagnostics.
        """
        payload = [self._serialize_policy(p) for p in self._policies]
        try:
            client = self._get_client()
            response = await client.put(settings.opa_data_path, json=payload)
            if response.status_code >= 400:
                logger.warning(
                    "OPA data push returned %s: %s",
                    response.status_code,
                    response.text,
                )
                return "failed"
            return "synced"
        except Exception as exc:
            logger.warning("OPA data push failed: %s", exc)
            return "failed"

    def _serialize_policy(self, policy: PolicySchema) -> Dict[str, Any]:
        condition = policy.condition.model_dump(exclude_none=False)
        if condition.get("sensitivity") is not None:
            condition["sensitivity"] = _coerce_sensitivity(condition["sensitivity"])
        return {
            "id": policy.id,
            "description": policy.description,
            "effect": policy.effect.value
            if isinstance(policy.effect, PolicyEffect)
            else str(policy.effect),
            "condition": condition,
        }

    # ── Evaluation API ───────────────────────────────────────────────────────

    async def evaluate_async(
        self, context: Dict[str, Any]
    ) -> List[PolicyEvaluationResult]:
        """Evaluate a request context against current policies.

        Delegates to OPA when `OPA_ENABLED` is true, otherwise falls back to
        the embedded Python evaluator. In both modes the contract is identical:
        returns the list of matching policy results, or raises
        ``PolicyViolationError`` if any policy denies the request.
        """
        from app.core.exceptions import PolicyViolationError

        canonical_ctx = self._canonicalize_context(context)
        logger.debug("[PolicyService] Evaluating context: %s", canonical_ctx)

        if settings.opa_enabled:
            try:
                return await self._evaluate_with_opa(canonical_ctx)
            except PolicyViolationError:
                raise
            except Exception as exc:
                logger.warning(
                    "OPA evaluation failed (%s); falling back to Python evaluator.",
                    exc,
                )

        return self._evaluate_local(canonical_ctx)

    def evaluate(self, context: Dict[str, Any]) -> List[PolicyEvaluationResult]:
        """Synchronous wrapper preserved for legacy callers and unit testing.

        Always uses the Python evaluator since OPA delegation requires async I/O.
        New code should call ``evaluate_async`` instead.
        """
        canonical_ctx = self._canonicalize_context(context)
        return self._evaluate_local(canonical_ctx)

    # ── OPA delegation ───────────────────────────────────────────────────────

    async def _evaluate_with_opa(
        self, context: Dict[str, Any]
    ) -> List[PolicyEvaluationResult]:
        from app.core.exceptions import PolicyViolationError

        client = self._get_client()
        body = {"input": {"context": context}}
        response = await client.post(settings.opa_policy_path, json=body)
        if response.status_code >= 400:
            raise RuntimeError(
                f"OPA returned HTTP {response.status_code}: {response.text}"
            )

        data = response.json() or {}
        result = data.get("result") or {}
        allow = bool(result.get("allow", True))
        block_ids = self._coerce_block_ids(result.get("block"))

        evaluation: List[PolicyEvaluationResult] = []
        denied: List[PolicyEvaluationResult] = []

        for policy in self._policies:
            if policy.id in block_ids:
                eval_result = PolicyEvaluationResult(
                    policy_id=policy.id,
                    effect=policy.effect,
                    decision="DENY",
                    description=policy.description,
                )
                evaluation.append(eval_result)
                denied.append(eval_result)
            elif self._matches(policy, context):
                evaluation.append(
                    PolicyEvaluationResult(
                        policy_id=policy.id,
                        effect=policy.effect,
                        decision="ALLOW",
                        description=policy.description,
                    )
                )

        if not allow and denied:
            first = denied[0]
            raise PolicyViolationError(
                policy_id=first.policy_id,
                description=first.description or "No description provided",
                results=evaluation,
            )

        return evaluation

    @staticmethod
    def _coerce_block_ids(raw: Any) -> set:
        """OPA serializes partial sets as either a JSON array or object."""
        if raw is None:
            return set()
        if isinstance(raw, dict):
            return {k for k, v in raw.items() if v}
        if isinstance(raw, (list, tuple, set)):
            return {str(item) for item in raw}
        return set()

    # ── Python fallback evaluator ────────────────────────────────────────────

    def _evaluate_local(
        self, context: Dict[str, Any]
    ) -> List[PolicyEvaluationResult]:
        from app.core.exceptions import PolicyViolationError

        results: List[PolicyEvaluationResult] = []

        for policy in self._policies:
            if not self._matches(policy, context):
                continue

            decision = "ALLOW"
            if self._should_block(policy, context):
                decision = "DENY"

            result = PolicyEvaluationResult(
                policy_id=policy.id,
                effect=policy.effect,
                decision=decision,
                description=policy.description,
            )
            results.append(result)

            if decision == "DENY":
                logger.warning(
                    "DENYING request due to policy violation: %s",
                    policy.id,
                )
                raise PolicyViolationError(
                    policy_id=policy.id,
                    description=policy.description or "No description provided",
                    results=results,
                )

        return results

    def _should_block(self, policy: PolicySchema, context: Dict[str, Any]) -> bool:
        effect = policy.effect
        service_type = context.get("service_type", "on-prem")

        if effect == PolicyEffect.DENY_ALL:
            return True
        if effect == PolicyEffect.DENY_CLOUD and service_type == "cloud":
            return True
        if effect == PolicyEffect.ALLOW_ONPREM_ONLY and service_type != "on-prem":
            return True
        return False

    def _matches(self, policy: PolicySchema, context: Dict[str, Any]) -> bool:
        condition = policy.condition

        if condition.sensitivity is not None:
            ctx_sensitivity = context.get("sensitivity")
            if _coerce_sensitivity(ctx_sensitivity) != _coerce_sensitivity(
                condition.sensitivity
            ):
                return False

        if condition.tenant is not None:
            if context.get("tenant") != condition.tenant:
                return False

        return True

    # ── Internal helpers ─────────────────────────────────────────────────────

    @staticmethod
    def _canonicalize_context(context: Dict[str, Any]) -> Dict[str, Any]:
        sensitivity = context.get("sensitivity")
        canonical = dict(context)
        canonical["service_type"] = canonical_service_type(
            context.get("service_type", "on-prem")
        )
        canonical["sensitivity"] = _coerce_sensitivity(sensitivity)
        return canonical
