"""ORM-level tenant scoping for SELECT queries (ORK-035, defense in depth with RLS)."""

from __future__ import annotations

import logging

from sqlalchemy import event
from sqlalchemy.orm import ORMExecuteState, Session, with_loader_criteria

from app.infrastructure.tenant_context import current_is_admin, current_tenant_id

logger = logging.getLogger(__name__)


def register_tenant_orm_filters() -> None:
    """Register global SELECT criteria when a tenant context is active."""

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

        from app.models.ai_request import AIRequestRecord
        from app.models.permission import PermissionAuditLog, TenantServicePermission
        from app.models.request_lifecycle import RequestLifecycleEvent
        from app.models.security_event import SecurityEvent
        from app.models.usage import UsageTokenLog

        scoped = (
            AIRequestRecord,
            UsageTokenLog,
            SecurityEvent,
            TenantServicePermission,
            PermissionAuditLog,
            RequestLifecycleEvent,
        )
        opts = [
            with_loader_criteria(
                ent,
                lambda cls, tenant_id=tid: cls.tenant_id == tenant_id,  # type: ignore[arg-type]
                include_aliases=True,
            )
            for ent in scoped
        ]
        execute_state.statement = execute_state.statement.options(*opts)
