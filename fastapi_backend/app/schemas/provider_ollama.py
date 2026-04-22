"""Normalized envelope for Ollama-compatible JSON responses (ORK-023)."""

from __future__ import annotations

from typing import Any, Dict, Optional

from pydantic import BaseModel, ConfigDict, Field


class OllamaMessageBlock(BaseModel):
    model_config = ConfigDict(extra="allow")

    role: Optional[str] = None
    content: Optional[str] = None


class OllamaProviderEnvelope(BaseModel):
    """Shape returned by ollama_client.chat(stream=False)."""

    model_config = ConfigDict(extra="forbid")

    response: Dict[str, Any]
    usage: Dict[str, Any] = Field(default_factory=dict)

    def message_content(self) -> str:
        msg = self.response.get("message")
        if isinstance(msg, dict):
            return str(msg.get("content") or "")
        return ""
