# app/core/exceptions.py
"""Domain exceptions raised by services and translated to HTTP responses by routers."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from app.schemas.policy import PolicyEvaluationResult


class DomainError(Exception):
    """Base class for domain-level exceptions."""


logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class IntentNotFoundError(DomainError):
    intent_name: str
    taxonomy_version: str

    def __str__(self) -> str:  # pragma: no cover
        return f"Intent '{self.intent_name}' not found in taxonomy v{self.taxonomy_version}"


@dataclass(frozen=True)
class ServiceNotFoundError(DomainError):
    service_id: str

    def __str__(self) -> str:  # pragma: no cover
        return f"Service '{self.service_id}' not found"


@dataclass(frozen=True)
class TenantNotAuthorizedError(DomainError):
    tenant_id: str
    service_id: str

    def __str__(self) -> str:  # pragma: no cover
        return f"Tenant '{self.tenant_id}' not authorized for service '{self.service_id}'"


@dataclass(frozen=True)
class ProviderError(DomainError):
    message: str

    def __str__(self) -> str:  # pragma: no cover
        return self.message


@dataclass(frozen=True)
class TenantIdMissingError(DomainError):
    """Raised when the token claims do not contain required tenant_id."""

    def __str__(self) -> str:  # pragma: no cover
        return "Missing X-Tenant-ID in token claims"


@dataclass(frozen=True)
class IntentMappingAlreadyExistsError(DomainError):
    intent_name: str

    def __str__(self) -> str:  # pragma: no cover
        return f"Intent '{self.intent_name}' already exists"


@dataclass(frozen=True)
class IntentMappingNotFoundError(DomainError):
    mapping_id: str

    def __str__(self) -> str:  # pragma: no cover
        return "Mapping not found"


@dataclass(frozen=True)
class PolicyViolationError(DomainError):
    policy_id: str
    description: str
    results: List[PolicyEvaluationResult]

    def __str__(self) -> str:  # pragma: no cover
        return f"Policy violation: {self.policy_id} - {self.description or 'No description provided'}"

