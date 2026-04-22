"""HMAC signing contract shared by Kong gateway-signature plugin and FastAPI (ORK-025).

When verifying an incoming signature, always use :func:`gateway_verify_signature`
rather than comparing with ``==``. Naive equality leaks byte-level timing
information and is exploitable; :func:`hmac.compare_digest` runs in constant
time regardless of where the two values diverge.
"""

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


def gateway_verify_signature(
    *,
    secret: str,
    method: str,
    path: str,
    timestamp: str,
    nonce: str,
    provided_signature: str,
) -> bool:
    """Constant-time comparison of a provided signature against the expected one.

    Returns False on any comparison mismatch, malformed input, or non-string
    ``provided_signature`` rather than raising, so callers can treat a False
    return as an auth failure without catching exceptions.
    """
    if not isinstance(provided_signature, str):
        return False
    expected = gateway_compute_signature(
        secret=secret,
        method=method,
        path=path,
        timestamp=timestamp,
        nonce=nonce,
    )
    return hmac.compare_digest(expected.encode("ascii"), provided_signature.encode("ascii"))
