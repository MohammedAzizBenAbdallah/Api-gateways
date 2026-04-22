"""ORM-level tenant scoping for SELECT queries (ORK-035, defense in depth with RLS)."""

from __future__ import annotations

import logging

from sqlalchemy import event
from sqlalchemy.orm import ORMExecuteState, Session, with_loader_criteria

from app.infrastructure.tenant_context import current_is_admin, current_tenant_id
from app.models.ai_request import AIRequestRecord
from app.models.permission import PermissionAuditLog, TenantServicePermission
from app.models.request_lifecycle import RequestLifecycleEvent
from app.models.security_event import SecurityEvent
from app.models.usage import UsageTokenLog

logger = logging.getLogger(__name__)

_SCOPED_MODELS: tuple[type, ...] = (
    AIRequestRecord,
    UsageTokenLog,
    SecurityEvent,
    TenantServicePermission,
    PermissionAuditLog,
    RequestLifecycleEvent,
)


def register_tenant_orm_filters() -> None:
    """Register global SELECT criteria when a tenant context is active.

    Fires on every ORM SELECT and injects a `WHERE tenant_id = :current_tenant`
    predicate for the scoped models unless:
      - the execution opts in with `bypass_tenant_filter=True`, or
      - the current request is authenticated as admin, or
      - no tenant context is set (e.g. startup / migrations).

    Callers are responsible for *setting* `current_tenant_id` / `current_is_admin`
    on every request and *resetting* them in a `finally` block so that
    connection-pool reuse cannot leak one tenant's scope into another's request.
    """

    @event.listens_for(Session, "do_orm_execute")
    def _tenant_scope_select(execute_state: ORMExecuteState) -> None:
        if not execute_state.is_select:
            return
        if execute_state.execution_options.get("bypass_tenant_filter"):
            return
        if current_is_admin.get():
            return
        tid = current_tenant_id.get()
        if not tid:
            return

        opts = [
            with_loader_criteria(
                ent,
                lambda cls, tenant_id=tid: cls.tenant_id == tenant_id,  # type: ignore[arg-type]
                include_aliases=True,
            )
            for ent in _SCOPED_MODELS
        ]
        execute_state.statement = execute_state.statement.options(*opts)
