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
    """Handles loading, validation and evaluation of YAML policies."""

    def __init__(self) -> None:
        self._policies: List[PolicySchema] = []
        self._version: str = "1.0.0"
        self._file_path: Optional[str] = None
        self._last_mtime: float = 0.0

    @property
    def policies(self) -> List[PolicySchema]:
        return self._policies

    @property
    def version(self) -> str:
        return self._version

    def load_policies(self, file_path: str) -> None:
        """
        Load policies from a YAML file.
        
        Args:
            file_path: Absolute path to the policies.yaml file.
            
        Raises:
            FileNotFoundError: If the file does not exist.
            ValueError: If the file is invalid YAML or doesn't match the schema.
        """
        if not os.path.exists(file_path):
            logger.error("Policy file not found: %s", file_path)
            raise FileNotFoundError(f"Policy file not found: {file_path}")

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f)

            if data is None:
                logger.warning("Policy file %s is empty", file_path)
                self._policies = []
                return

            # Validate against Pydantic schema
            policy_file = PolicyFileSchema(**data)
            self._policies = policy_file.policies
            self._version = policy_file.version
            self._file_path = file_path
            self._last_mtime = os.path.getmtime(file_path)
            
            logger.info(
                "Successfully loaded %d policies (version %s) from %s",
                len(self._policies),
                self._version,
                file_path,
            )

        except yaml.YAMLError as e:
            logger.error("YAML parsing error in %s: %s", file_path, str(e))
            raise ValueError(f"Invalid YAML in policy file: {str(e)}") from e
            
        except ValidationError as e:
            # Format Pydantic errors for better readability
            errors = e.errors()
            formatted_errors = []
            for err in errors:
                loc = " -> ".join(str(x) for x in err["loc"])
                msg = err["msg"]
                formatted_errors.append(f"[{loc}]: {msg}")
            
            error_msg = "; ".join(formatted_errors)
            logger.error("Schema validation error in %s: %s", file_path, error_msg)
            raise ValueError(f"Policy schema validation failed: {error_msg}") from e

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
        self.reload_if_needed()
        logger.info("[PolicyService] Evaluating context: %s", context)
        
        from app.core.exceptions import PolicyViolationError
        
        results: List[PolicyEvaluationResult] = []
        
        for policy in self._policies:
            if self._matches(policy, context):
                logger.info(
                    "Context matches policy '%s' (Effect: %s)",
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
        
        logger.info("[PolicyService] Policy '%s' matched successfully", policy.id)
        return True

    def reload_if_needed(self) -> None:
        """Reload policies if the file has been modified since last load."""
        if not self._file_path or not os.path.exists(self._file_path):
            return

        try:
            current_mtime = os.path.getmtime(self._file_path)
            if current_mtime > self._last_mtime:
                logger.info(
                    "[PolicyService] Policy file changed (mtime: %s > %s). Reloading...",
                    current_mtime,
                    self._last_mtime,
                )
                self.load_policies(self._file_path)
        except Exception as e:
            logger.error("[PolicyService] Failed to hot-reload policies: %s", str(e))
