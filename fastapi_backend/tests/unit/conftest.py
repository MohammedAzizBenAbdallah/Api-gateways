"""Shared unit-test setup.

Pre-populates the environment with the variables required by `Settings()` so
that importing app modules under test does not trigger a `ValidationError`.
These values are inert (not used by unit tests) and are safe defaults.
"""

from __future__ import annotations

import os

_DEFAULTS = {
    "PLATFORM_DB_URL": "postgresql://test:test@localhost:5432/test",
    "KEYCLOAK_URL": "http://localhost:8080",
    "KEYCLOAK_REALM": "test",
    "CORS_ORIGIN": "http://localhost",
}

for key, value in _DEFAULTS.items():
    os.environ.setdefault(key, value)
