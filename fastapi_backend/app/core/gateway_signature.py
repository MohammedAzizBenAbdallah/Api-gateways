"""HMAC signing contract shared by Kong gateway-signature plugin and FastAPI (ORK-025)."""

from __future__ import annotations

import base64
import hashlib
import hmac


def gateway_canonical_string(*, method: str, path: str, timestamp: str, nonce: str) -> str:
    return f"{method}|{path}|{timestamp}|{nonce}"


def gateway_compute_signature(*, secret: str, method: str, path: str, timestamp: str, nonce: str) -> str:
    msg = gateway_canonical_string(method=method, path=path, timestamp=timestamp, nonce=nonce)
    digest = hmac.new(secret.encode("utf-8"), msg.encode("utf-8"), hashlib.sha256).digest()
    return base64.b64encode(digest).decode("ascii")
