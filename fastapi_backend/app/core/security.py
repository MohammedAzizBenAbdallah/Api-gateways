# app/core/security.py
"""JWT verification and authorization helpers for routers."""

from __future__ import annotations

import asyncio
import httpx
import logging
from typing import Any, Dict, Optional

from jose import jwt
from fastapi import Depends, HTTPException, Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.config import settings

logger = logging.getLogger(__name__)

security = HTTPBearer()

_jwks_cache: Optional[Dict[str, Any]] = None
_jwks_lock = asyncio.Lock()


async def _fetch_jwks() -> Dict[str, Any]:
    jwks_url = (
        f"{settings.keycloak_url}/realms/{settings.keycloak_realm}/protocol/openid-connect/certs"
    )
    async with httpx.AsyncClient() as client:
        response = await client.get(jwks_url, timeout=10.0)
        response.raise_for_status()
        return response.json()


async def get_jwks() -> Dict[str, Any]:
    global _jwks_cache
    if _jwks_cache is not None:
        return _jwks_cache

    async with _jwks_lock:
        if _jwks_cache is not None:
            return _jwks_cache
        _jwks_cache = await _fetch_jwks()
        return _jwks_cache


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Security(security),
) -> Dict[str, Any]:
    token = credentials.credentials
    try:
        jwks = await get_jwks()

        unverified_header = jwt.get_unverified_header(token)
        kid = unverified_header.get("kid")
        rsa_key: Dict[str, Any] = {}
        for key in jwks.get("keys", []):
            if key.get("kid") == kid:
                rsa_key = {
                    "kty": key.get("kty"),
                    "kid": key.get("kid"),
                    "use": key.get("use"),
                    "n": key.get("n"),
                    "e": key.get("e"),
                }
                break

        if not rsa_key:
            raise jwt.JWTError("No matching JWKS key found for token 'kid'")

        # List all possible valid issuers (internal, localhost, and public IP)
        valid_issuers = [
            f"{settings.keycloak_url}/realms/{settings.keycloak_realm}",
            f"http://localhost:8080/realms/{settings.keycloak_realm}",
            f"http://197.14.4.163:8080/realms/{settings.keycloak_realm}",
        ]

        # Decode without audience check initially to inspect payload,
        # or use options to disable specific checks if they are too strict.
        payload = jwt.decode(
            token,
            rsa_key,
            algorithms=["RS256"],
            # Relaxing audience check as it varies by Keycloak config
            options={
                "verify_iss": True,
                "verify_aud": False,  # We'll check roles instead
                "verify_exp": True
            },
        )

        iss = payload.get("iss")
        if iss not in valid_issuers:
            logger.warning("Issuer mismatch: %s. Expected one of: %s", iss, valid_issuers)
            # For development, we can be more lenient if the signature matches the JWKS
            # but it is better to list the known valid issuers.
            if settings.environment != "production":
                 logger.info("Proceeding despite issuer mismatch in non-production environment")
            else:
                raise jwt.JWTError(f"Invalid issuer: {iss}")

        return payload
    except Exception as exc:
        logger.warning("JWT verification failed: %s", exc)
        global _jwks_cache
        _jwks_cache = None
        raise HTTPException(status_code=401, detail=f"Invalid token: {str(exc)}")


def require_admin(user: Dict[str, Any] = Depends(get_current_user)) -> Dict[str, Any]:
    """Enforce the 'admin' role from Keycloak realm_access.roles."""

    roles = user.get("realm_access", {}).get("roles", [])
    if "admin" not in roles:
        raise HTTPException(status_code=403, detail="Forbidden: Admin role required")
    return user

