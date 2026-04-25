# app/services/policy_service.py
"""Service for loading and evaluating governance policies via OPA.

Evaluation is delegated to an external Open Policy Agent (OPA) instance over
HTTP. A pure-Python evaluator is kept as a rollback path behind the
``OPA_ENABLED`` and ``OPA_ALLOW_LOCAL_FALLBACK`` feature flags so the service
can degrade gracefully when explicitly allowed.

Reliability controls (settings):

* ``OPA_STRICT_SYNC`` — when true, ``sync_from_db`` raises ``PolicySyncError``
  if the push to OPA fails, so the caller (startup, admin reload, admin CRUD)
  can surface the error instead of silently leaving OPA on stale data.
* ``OPA_ALLOW_LOCAL_FALLBACK`` — when true, runtime evaluation may fall back
  to the embedded Python evaluator if OPA is unreachable or returns a
  malformed response. When false, runtime errors propagate as
  ``PolicyEvaluationError`` (fail-closed-friendly).
* ``OPA_FAIL_CLOSED`` — when true, runtime evaluation refuses to query OPA
  if the local cache hash diverges from the last successfully pushed hash,
  preventing decisions over stale data.
"""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set, TYPE_CHECKING

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

# Required top-level fields the OPA decision result must contain.
_REQUIRED_RESULT_FIELDS = ("allow",)


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

        # Observability / consistency state. These are exposed via
        # ``get_status()`` and surfaced through the admin API so operators can
        # see whether the local cache and OPA are in sync.
        self._local_hash: Optional[str] = None
        self._last_pushed_hash: Optional[str] = None
        self._last_pushed_version: Optional[str] = None
        self._last_sync_ok: Optional[bool] = None
        self._last_sync_at: Optional[str] = None
        self._last_sync_error: Optional[str] = None

    @property
    def policies(self) -> List[PolicySchema]:
        return self._policies

    @property
    def version(self) -> str:
        return self._version

    def get_status(self) -> Dict[str, Any]:
        """Snapshot of policy-cache / OPA sync state for the admin UI."""
        return {
            "opa_enabled": settings.opa_enabled,
            "opa_strict_sync": settings.opa_strict_sync,
            "opa_allow_local_fallback": settings.opa_allow_local_fallback,
            "opa_fail_closed": settings.opa_fail_closed,
            "policy_count": len(self._policies),
            "version": self._version,
            "local_hash": self._local_hash,
            "last_pushed_hash": self._last_pushed_hash,
            "last_pushed_version": self._last_pushed_version,
            "last_sync_ok": self._last_sync_ok,
            "last_sync_at": self._last_sync_at,
            "last_sync_error": self._last_sync_error,
            "in_sync": (
                self._last_sync_ok is True
                and self._local_hash is not None
                and self._local_hash == self._last_pushed_hash
            ),
        }

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

    async def sync_from_db(self, db: "AsyncSession") -> Dict[str, Any]:
        """Refresh the in-memory cache from DB and push it to OPA data API.

        Behavior:
          * Always rebuilds the local in-memory cache from DB.
          * If ``OPA_ENABLED`` is true, attempts to push the canonical bundle
            ``{"items": [...], "version": ..., "hash": ...}`` to OPA.
          * On push failure, records ``last_sync_ok=False`` and the error
            detail. If ``OPA_STRICT_SYNC`` is true, raises ``PolicySyncError``
            so callers (startup / admin reload / admin CRUD) fail loudly.
        """
        from app.core.exceptions import PolicySyncError
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

        self._local_hash = self._compute_policy_hash(self._policies, self._version)

        opa_status = "disabled"
        push_error: Optional[str] = None

        if settings.opa_enabled:
            try:
                await self._push_policies_to_opa()
                opa_status = "synced"
                self._last_pushed_hash = self._local_hash
                self._last_pushed_version = self._version
                self._last_sync_ok = True
                self._last_sync_error = None
            except Exception as exc:
                push_error = str(exc)
                opa_status = "failed"
                self._last_sync_ok = False
                self._last_sync_error = push_error
                logger.error(
                    "OPA data push failed (strict=%s): %s",
                    settings.opa_strict_sync,
                    push_error,
                )

        self._last_sync_at = datetime.now(timezone.utc).isoformat()

        logger.info(
            "Synced %d active policies (opa=%s, hash=%s, version=%s).",
            len(self._policies),
            opa_status,
            (self._local_hash or "")[:12],
            self._version,
        )

        if push_error and settings.opa_strict_sync:
            raise PolicySyncError(reason="opa_push_failed", detail=push_error)

        return {
            "total_in_db": len(db_policies),
            "active_synced": len(self._policies),
            "version": self._version,
            "hash": self._local_hash,
            "opa": opa_status,
            "in_sync": self._last_sync_ok is True
            and self._local_hash == self._last_pushed_hash,
            "error": push_error,
        }

    async def _push_policies_to_opa(self) -> None:
        """Push the canonical policy bundle as an OPA data document.

        Raises on any non-2xx status or transport error so callers can decide
        whether to fail-fast (strict) or mark the service as degraded.
        """
        bundle = self._serialize_policy_bundle()
        client = self._get_client()
        try:
            response = await client.put(settings.opa_data_path, json=bundle)
        except httpx.HTTPError as exc:
            raise RuntimeError(f"OPA data push transport error: {exc}") from exc

        if response.status_code >= 400:
            raise RuntimeError(
                f"OPA data push returned HTTP {response.status_code}: "
                f"{response.text[:300]}"
            )

    # ── Serialization / hashing ──────────────────────────────────────────────

    def _serialize_policy_bundle(self) -> Dict[str, Any]:
        """Canonical OPA data shape with deterministic version + hash metadata."""
        items = [self._serialize_policy(p) for p in self._policies]
        return {
            "items": items,
            "version": self._version,
            "hash": self._local_hash
            or self._compute_policy_hash(self._policies, self._version),
        }

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

    @staticmethod
    def _compute_policy_hash(policies: List[PolicySchema], version: str) -> str:
        """Deterministic SHA-256 over the active policy set + version."""
        normalized = []
        for p in policies:
            condition = p.condition.model_dump(exclude_none=False)
            if condition.get("sensitivity") is not None:
                condition["sensitivity"] = _coerce_sensitivity(
                    condition["sensitivity"]
                )
            effect_value = (
                p.effect.value if isinstance(p.effect, PolicyEffect) else str(p.effect)
            )
            normalized.append(
                {
                    "id": p.id,
                    "description": p.description,
                    "effect": effect_value,
                    "condition": condition,
                }
            )
        normalized.sort(key=lambda item: item["id"] or "")
        canonical = json.dumps(
            {"version": version, "items": normalized},
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        )
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    # ── Evaluation API ───────────────────────────────────────────────────────

    async def evaluate_async(
        self, context: Dict[str, Any]
    ) -> List[PolicyEvaluationResult]:
        """Evaluate a request context against current policies.

        Delegates to OPA when ``OPA_ENABLED`` is true. Behavior on OPA failure:
          * If ``OPA_ALLOW_LOCAL_FALLBACK`` is true, falls back to the embedded
            Python evaluator and logs a warning.
          * Otherwise raises ``PolicyEvaluationError`` (fail-closed-friendly).

        If ``OPA_FAIL_CLOSED`` is true and the local cache diverges from the
        last hash successfully pushed to OPA, raises ``PolicyEvaluationError``
        before contacting OPA so we never decide on stale data.

        ``PolicyViolationError`` is always re-raised unchanged.
        """
        from app.core.exceptions import PolicyEvaluationError, PolicyViolationError

        canonical_ctx = self._canonicalize_context(context)
        logger.debug("[PolicyService] Evaluating context: %s", canonical_ctx)

        if not settings.opa_enabled:
            return self._evaluate_local(canonical_ctx)

        if settings.opa_fail_closed and not self._is_in_sync():
            raise PolicyEvaluationError(
                reason="opa_cache_out_of_sync",
                detail=(
                    f"local_hash={self._local_hash} "
                    f"last_pushed_hash={self._last_pushed_hash} "
                    f"last_sync_ok={self._last_sync_ok}"
                ),
            )

        try:
            return await self._evaluate_with_opa(canonical_ctx)
        except PolicyViolationError:
            raise
        except PolicyEvaluationError:
            raise
        except Exception as exc:
            if settings.opa_allow_local_fallback:
                logger.warning(
                    "OPA evaluation failed (%s); falling back to Python evaluator.",
                    exc,
                )
                return self._evaluate_local(canonical_ctx)
            logger.error(
                "OPA evaluation failed and local fallback is disabled: %s", exc
            )
            raise PolicyEvaluationError(
                reason="opa_unreachable_or_invalid", detail=str(exc)
            ) from exc

    def evaluate(self, context: Dict[str, Any]) -> List[PolicyEvaluationResult]:
        """Synchronous wrapper preserved for legacy callers and unit testing.

        Always uses the Python evaluator since OPA delegation requires async I/O.
        New code should call ``evaluate_async`` instead.
        """
        canonical_ctx = self._canonicalize_context(context)
        return self._evaluate_local(canonical_ctx)

    def _is_in_sync(self) -> bool:
        return (
            self._last_sync_ok is True
            and self._local_hash is not None
            and self._local_hash == self._last_pushed_hash
        )

    # ── OPA delegation ───────────────────────────────────────────────────────

    async def _evaluate_with_opa(
        self, context: Dict[str, Any]
    ) -> List[PolicyEvaluationResult]:
        from app.core.exceptions import PolicyEvaluationError, PolicyViolationError

        client = self._get_client()
        body = {"input": {"context": context}}
        response = await client.post(settings.opa_policy_path, json=body)
        if response.status_code >= 400:
            raise RuntimeError(
                f"OPA returned HTTP {response.status_code}: {response.text[:300]}"
            )

        try:
            data = response.json()
        except ValueError as exc:
            raise PolicyEvaluationError(
                reason="opa_invalid_json", detail=str(exc)
            ) from exc

        allow, block_ids = self._parse_opa_result(data)

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
    def _parse_opa_result(payload: Any) -> tuple[bool, Set[str]]:
        """Strictly validate the OPA response and extract (allow, block_ids).

        Raises ``PolicyEvaluationError`` on any structural deviation. We do
        NOT default missing fields to permissive values; an unexpected shape
        from OPA must surface as an error rather than a silent allow.
        """
        from app.core.exceptions import PolicyEvaluationError

        if not isinstance(payload, dict):
            raise PolicyEvaluationError(
                reason="opa_response_not_object",
                detail=f"got {type(payload).__name__}",
            )
        if "result" not in payload:
            raise PolicyEvaluationError(
                reason="opa_response_missing_result",
                detail=f"keys={list(payload.keys())}",
            )

        result = payload["result"]
        if not isinstance(result, dict):
            raise PolicyEvaluationError(
                reason="opa_result_not_object",
                detail=f"got {type(result).__name__}",
            )

        for field in _REQUIRED_RESULT_FIELDS:
            if field not in result:
                raise PolicyEvaluationError(
                    reason="opa_result_missing_field",
                    detail=f"missing={field}",
                )

        allow = result["allow"]
        if not isinstance(allow, bool):
            raise PolicyEvaluationError(
                reason="opa_result_allow_not_bool",
                detail=f"got {type(allow).__name__}",
            )

        block_ids = PolicyService._coerce_block_ids(result.get("block"))
        return allow, block_ids

    @staticmethod
    def _coerce_block_ids(raw: Any) -> Set[str]:
        """OPA serializes partial sets as either a JSON array or object.

        Strict: any other type raises ``PolicyEvaluationError`` so we never
        silently treat a malformed block payload as "no policies blocked".
        """
        from app.core.exceptions import PolicyEvaluationError

        if raw is None:
            return set()
        if isinstance(raw, dict):
            return {str(k) for k, v in raw.items() if v}
        if isinstance(raw, (list, tuple, set)):
            return {str(item) for item in raw}
        raise PolicyEvaluationError(
            reason="opa_result_block_invalid_type",
            detail=f"got {type(raw).__name__}",
        )

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
