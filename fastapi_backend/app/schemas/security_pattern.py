# app/schemas/security_pattern.py
"""Pydantic schemas for Security Patterns."""

from pydantic import BaseModel, ConfigDict
from typing import Optional

class SecurityPatternBase(BaseModel):
    name: str
    pattern: str
    weight: float = 1.0
    description: Optional[str] = None
    is_active: bool = True

class SecurityPatternCreate(SecurityPatternBase):
    pass

class SecurityPatternUpdate(BaseModel):
    name: Optional[str] = None
    pattern: Optional[str] = None
    weight: Optional[float] = None
    description: Optional[str] = None
    is_active: Optional[bool] = None

class SecurityPatternOut(SecurityPatternBase):
    id: int
    
    model_config = ConfigDict(from_attributes=True)
