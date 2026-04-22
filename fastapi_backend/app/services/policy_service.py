# app/services/policy_service.py
"""Service for loading and evaluating governance policies."""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, List, Optional

import yaml
from pydantic import ValidationError

from app.schemas.policy import PolicyEffect, PolicyFileSchema, PolicySchema, PolicyEvaluationResult

logger = logging.getLogger(__name__)


class PolicyService:
    """Handles loading, validation and evaluation of governance policies from the DB."""

    def __init__(self) -> None:
        self._policies: List[PolicySchema] = []
        self._version: str = "1.0.0"

    @property
    def policies(self) -> List[PolicySchema]:
        return self._policies

    @property
    def version(self) -> str:
        return self._version

    async def sync_from_db(self, db: AsyncSession) -> dict:
        """
        Synchronize the in-memory policy cache with the database.
        
        Returns:
            A dictionary with sync statistics.
        """
        from app.repositories.policy_repository import list_policies
        
        logger.info("[PolicyService] Syncing policies from database...")
        db_policies = await list_policies(db)
        
        new_policies = []
        # Filter for active policies and convert to Schema
        for p in db_policies:
            if not p.is_active:
                continue
            
            try:
                # p.condition is already a dict (JSON column)
                policy_schema = PolicySchema(
                    id=p.id,
                    description=p.description,
                    condition=p.condition, # Pydantic will validate this dict
                    effect=p.effect
                )
                new_policies.append(policy_schema)
            except Exception as e:
                logger.error("Failed to parse policy %s from DB: %s", p.id, str(e))

        self._policies = new_policies
        # Use the version from the first policy if available, or default
        if db_policies:
            self._version = db_policies[0].version
        
        logger.info(
            "Successfully synced %d active policies from database.",
            len(self._policies)
        )
        return {
            "total_in_db": len(db_policies),
            "active_synced": len(self._policies),
            "version": self._version
        }

    def evaluate(self, context: Dict[str, Any]) -> List[PolicyEvaluationResult]:
        """
        Evaluate context against loaded policies.
        
        Args:
            context: A dictionary containing request attributes (e.g., sensitivity, tenant, service_type).
            
        Returns:
            A list of PolicyEvaluationResult for all matching policies.
            
        Raises:
            PolicyViolationError: If a matching policy should block the request.
        """
        logger.debug("[PolicyService] Evaluating context: %s", context)
        
        from app.core.exceptions import PolicyViolationError
        
        results: List[PolicyEvaluationResult] = []
        
        for policy in self._policies:
            if self._matches(policy, context):
                logger.debug(
                    "Policy '%s' matched (effect=%s)",
                    policy.id,
                    policy.effect,
                )
                
                decision = "ALLOW"
                if self._should_block(policy, context):
                    decision = "DENY"
                
                result = PolicyEvaluationResult(
                    policy_id=policy.id,
                    effect=policy.effect,
                    decision=decision,
                    description=policy.description
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
                        results=results
                    )
        
        return results

    def _should_block(self, policy: PolicySchema, context: Dict[str, Any]) -> bool:
        """Determine if a matching policy should result in a blocking action."""
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
        """Check if the context satisfies the policy conditions."""
        condition = policy.condition
        
        # Sensitivity check
        if condition.sensitivity is not None:
            context_sensitivity = context.get("sensitivity")
            if str(context_sensitivity) != str(condition.sensitivity):
                return False
        
        # Tenant check
        if condition.tenant is not None:
            if context.get("tenant") != condition.tenant:
                return False
        
        logger.debug("Policy '%s' conditions satisfied", policy.id)
        return True
