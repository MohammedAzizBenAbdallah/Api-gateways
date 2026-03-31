# app/infrastructure/ai_provider/ollama_client.py
"""All external AI provider (Ollama-style) HTTP calls live here."""

from __future__ import annotations

import json
import logging
from typing import Any, AsyncIterator, Dict, List, Optional, Union

import httpx

logger = logging.getLogger(__name__)


async def chat(
    provider_url: str,
    model: Optional[str],
    messages: List[Dict[str, Any]],
    stream: bool,
) -> Union[Dict[str, Any], AsyncIterator[Dict[str, Any]]]:
    """
    Call an Ollama-compatible provider.

    Returns a JSON dict when stream=False, otherwise returns an async iterator of
    chunks formatted like: {"token": str, "done": bool}.
    """

    if not stream:
        outbound_body: Dict[str, Any] = {"messages": messages}
        # Match the historical behavior:
        # - Ollama-compatible providers send {model, messages, stream: False}
        # - Other providers receive only {messages}
        if model is not None:
            outbound_body["model"] = model
            outbound_body["stream"] = False

        async with httpx.AsyncClient() as client:
            resp = await client.post(provider_url, json=outbound_body, timeout=120.0)
            resp.raise_for_status()
            return resp.json()

    async def _generator() -> AsyncIterator[Dict[str, Any]]:
        outbound_body: Dict[str, Any] = {"messages": messages}
        if model is not None:
            outbound_body["model"] = model
        outbound_body["stream"] = True

        async with httpx.AsyncClient() as client:
            try:
                async with client.stream(
                    "POST",
                    provider_url,
                    json=outbound_body,
                    timeout=None,
                ) as r:
                    async for line in r.aiter_lines():
                        if not line.strip():
                            continue
                        try:
                            chunk = json.loads(line)
                        except json.JSONDecodeError:
                            continue

                        token = chunk.get("message", {}).get("content", "") or ""
                        done = bool(chunk.get("done", False))
                        yield {"token": token, "done": done}
            except Exception as exc:  # pragma: no cover
                logger.exception("AI provider stream failed: %s", exc)
                raise

    return _generator()

