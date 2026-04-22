"""Request-scoped tenant / admin flags for ORM tenant filters (ORK-035)."""

from __future__ import annotations

from contextvars import ContextVar
from typing import Optional

current_tenant_id: ContextVar[Optional[str]] = ContextVar("current_tenant_id", default=None)
current_is_admin: ContextVar[bool] = ContextVar("current_is_admin", default=False)
