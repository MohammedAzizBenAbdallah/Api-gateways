"""Request/response schemas — exactly one intent label per response."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

SourceKind = Literal["cache", "model", "fallback", "heuristic"]


class ClassifyRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str = Field(..., min_length=1, max_length=32_000)
    tenant_id: str | None = None
    environment: str | None = Field(default=None, description="e.g. dev|prod")


class ClassifyResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    intent_label: str
    confidence: float = Field(ge=0.0, le=1.0)
    source: SourceKind
    taxonomy_version: str
    model_id: str
