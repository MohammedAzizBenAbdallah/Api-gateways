# app/schemas/policy.py
"""Schemas for YAML policies."""

from __future__ import annotations
from enum import Enum
from typing import List, Optional
from pydantic import BaseModel, ConfigDict
from app.schemas.ai_request import SensitivityLevel


class PolicyEffect(str, Enum):
    """Available effects for governance policies."""
    ALLOW_ONPREM_ONLY = "allow_onprem_only"
    DENY_CLOUD = "deny_cloud"
    ALLOW_ALL = "allow_all"
    DENY_ALL = "deny_all"


class PolicyConditionSchema(BaseModel):
    """Condition block for policies (IF)."""
    model_config = ConfigDict(extra="forbid")
    
    sensitivity: Optional[SensitivityLevel] = None
    tenant: Optional[str] = None


class PolicySchema(BaseModel):
    """A single governance policy."""
    model_config = ConfigDict(extra="forbid")
    
    id: str
    description: Optional[str] = None
    condition: PolicyConditionSchema
    effect: PolicyEffect


class PolicyEvaluationResult(BaseModel):
    """Outcome of evaluating a single policy."""
    policy_id: str
    effect: PolicyEffect
    decision: str  # ALLOW, DENY, SKIP
    description: Optional[str] = None


class PolicyFileSchema(BaseModel):
    """Root structure of a policies.yaml file."""
    model_config = ConfigDict(extra="forbid")
    
    version: str = "1.0.0"
    policies: List[PolicySchema]


class GovernancePolicyCreate(BaseModel):
    """Schema for creating a storage-backed policy."""
    description: Optional[str] = None
    condition: PolicyConditionSchema
    effect: PolicyEffect
    is_active: bool = True
    version: str = "1.0.0"


class GovernancePolicyUpdate(BaseModel):
    """Schema for updating a storage-backed policy."""
    description: Optional[str] = None
    condition: Optional[PolicyConditionSchema] = None
    effect: Optional[PolicyEffect] = None
    is_active: Optional[bool] = None
    version: Optional[str] = None


class GovernancePolicyResponse(BaseModel):
    """Response schema for a governance policy."""
    model_config = ConfigDict(from_attributes=True)
    
    id: str
    description: Optional[str] = None
    condition: PolicyConditionSchema
    effect: PolicyEffect
    is_active: bool
    version: str
