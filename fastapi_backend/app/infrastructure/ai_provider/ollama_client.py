# app/infrastructure/ai_provider/ollama_client.py
"""All external AI provider (Ollama-style) HTTP calls live here."""

from __future__ import annotations

import json
import logging
from typing import Any, AsyncIterator, Dict, List, Optional, Union

import httpx

logger = logging.getLogger(__name__)

# Module-level persistent client — avoids a new TCP handshake on every request.
# Closed gracefully at app shutdown via close_client() wired into main.py lifespan.
_http_client = httpx.AsyncClient(
    timeout=httpx.Timeout(120.0, connect=10.0),
)


async def close_client() -> None:
    """Release the shared connection pool. Call from app lifespan finally."""
    await _http_client.aclose()


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
        if model is not None:
            outbound_body["model"] = model
            outbound_body["stream"] = False

        resp = await _http_client.post(provider_url, json=outbound_body)
        resp.raise_for_status()
        data = resp.json()

        usage = {
            "prompt_eval_count": data.get("prompt_eval_count", 0),
            "eval_count": data.get("eval_count", 0),
        }
        return {"response": data, "usage": usage}

    async def _generator() -> AsyncIterator[Dict[str, Any]]:
        outbound_body: Dict[str, Any] = {"messages": messages}
        if model is not None:
            outbound_body["model"] = model
        outbound_body["stream"] = True

        try:
            async with _http_client.stream(
                "POST",
                provider_url,
                json=outbound_body,
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

                    usage = None
                    if done:
                        usage = {
                            "prompt_eval_count": chunk.get("prompt_eval_count", 0),
                            "eval_count": chunk.get("eval_count", 0),
                        }

                    yield {"token": token, "done": done, "usage": usage}
        except Exception as exc:  # pragma: no cover
            logger.exception("AI provider stream failed: %s", exc)
            raise

    return _generator()
