# Audit Remediation Plan (v2)

## Context

Source audit: [backlog_audit_report.md](backlog_audit_report.md). This revision changes the approach to finding #1 after feedback that the frontend needs intent data for non-admin users. All other findings keep the same fix as before.

## Findings and Fixes

### 1. Privilege escalation on intent mappings (CRITICAL) - REVISED

File: [fastapi_backend/app/api/admin/intent_mappings.py](fastapi_backend/app/api/admin/intent_mappings.py)

#### Why the previous fix was wrong

Reverting to `require_admin` would break the UI: non-admin users need the list of intents to populate the chat's intent dropdown. So we cannot lock the endpoint fully.

#### Why the current code is wrong

Returning the full admin payload to any authenticated user leaks:

- `service_id` (e.g. `ollama-DeepSeekCoder`) - internal provider / model topology.
- `created_by` - admin usernames / emails.
- `id`, `created_at`, `updated_at` - internal metadata the frontend does not need.
- Inactive rows - stale or disabled routes a user should not see in their picker.

#### New approach: split the surface by audience

Keep one source of truth but expose two views with different schemas and different auth:

- **Admin view** (unchanged location): `GET /admin/intent-mappings` and `GET /admin/intent-mappings/{id}` - full `IntentMappingResponseSchema`, gated by `require_admin`. Revert the two GETs to `require_admin` and drop the misleading "any authenticated user may read" comment.
- **Public catalog view** (new): `GET /ai/intents` - returns only the fields a chat UI needs, gated by `get_current_user`, filtered to `is_active=True`.

New slim schema in [fastapi_backend/app/schemas/intent_mapping.py](fastapi_backend/app/schemas/intent_mapping.py):

```python
class IntentCatalogItemSchema(BaseModel):
    intent_name: str
```

(Leave room to add an optional `display_name` / `description` column later without breaking the contract.)

New handler in [fastapi_backend/app/api/ai.py](fastapi_backend/app/api/ai.py) (or a new `app/api/intents.py` router mounted at `/ai`):

```python
@router.get("/intents", response_model=list[IntentCatalogItemSchema],
            dependencies=[Depends(verify_kong_header)])
async def list_intent_catalog(
    db: AsyncSession = Depends(get_db_with_user),
    current_user: Dict[str, Any] = Depends(get_current_user),
    intent_mappings_service: IntentMappingsService = Depends(get_intent_mappings_service),
) -> list[IntentCatalogItemSchema]:
    mappings = await intent_mappings_service.list_mappings(db)
    return [IntentCatalogItemSchema(intent_name=m.intent_name)
            for m in mappings if m.is_active]
```

Notes:

- Service layer does not need changes; filtering is a response-shape concern kept at the API layer.
- The frontend switches from `GET /admin/intent-mappings` to `GET /ai/intents`.
- Update any frontend client code / generated types accordingly.

### 2. Broken transaction atomicity in lifecycle repo (CRITICAL) - unchanged

File: [fastapi_backend/app/repositories/request_lifecycle_repository.py](fastapi_backend/app/repositories/request_lifecycle_repository.py)

- Remove `await session.commit()` at line 31.
- Replace with `await session.flush()`.
- Add docstring: "Caller owns the transaction; this only stages the row and flushes."

### 3. Misleading service_type in seed data - unchanged

File: [backend/scripts/init-platform-db.sql](backend/scripts/init-platform-db.sql) line 116

- Change `'cloud'` to `'on-prem'` for `ollama-DeepSeekCoder`.

### 4. Tenant ORM filter: hoist imports + fix latent no-op - unchanged

File: [fastapi_backend/app/infrastructure/db/tenant_filters.py](fastapi_backend/app/infrastructure/db/tenant_filters.py)

- Hoist model imports to module top, cache the `scoped` tuple.
- Add `TenantContextMiddleware` in [fastapi_backend/app/core/middleware.py](fastapi_backend/app/core/middleware.py) that sets `current_tenant_id` / `current_is_admin` from the JWT claims and resets via `ContextVar.reset(token)` in `finally`.
- Register the middleware in [fastapi_backend/app/main.py](fastapi_backend/app/main.py).
- Mirror the same set/reset inside `get_db_with_user` in [fastapi_backend/app/infrastructure/db/session.py](fastapi_backend/app/infrastructure/db/session.py) so RLS session vars and ORM filters stay in sync.

### 5. Information disclosure in AI error responses - unchanged

File: [fastapi_backend/app/api/ai.py](fastapi_backend/app/api/ai.py) lines 91-111

- Drop `matched_patterns` from the `SecurityViolationError` HTTP detail; log it server-side at WARNING.
- Keep `detected_pii_types` (user-facing categories like `EMAIL`, `SSN`).
- Short comment explaining the split so the field is not re-added.

### 6. Timing-safe signature verification - unchanged

File: [fastapi_backend/app/core/gateway_signature.py](fastapi_backend/app/core/gateway_signature.py)

- Add `gateway_verify_signature(*, secret, method, path, timestamp, nonce, provided_signature) -> bool` using `hmac.compare_digest`.
- Update module docstring to instruct callers to use the verifier rather than `==`.

## Quality Pass

- Remove dead `_ = current_user` / `_ = admin_user` lines in [intent_mappings.py](fastapi_backend/app/api/admin/intent_mappings.py) now that the dependency itself is the auth gate.
- Drop unused imports from [intent_mappings.py](fastapi_backend/app/api/admin/intent_mappings.py) after the revert (keep `get_current_user` only if the new catalog handler lives in the same module).

## Verification

- Unit test: `GET /admin/intent-mappings` returns 403 for a non-admin token, 200 for admin.
- Unit test: `GET /ai/intents` returns 200 for a normal user and the payload contains only `intent_name`, only active entries, no `service_id` / `created_by` / `id`.
- Unit test: `append_lifecycle_event` does not commit; a rollback by the caller removes the staged row.
- Unit test: `gateway_verify_signature` returns False on tampered input, True on valid.
- Unit test: `SecurityViolationError` response body has no `matched_patterns` key.
- Integration smoke: seed row `ollama-DeepSeekCoder` has `service_type='on-prem'`.
- `ruff check` and `mypy` pass on touched files.

## Out of Scope

- Adding a real `display_name` / `description` column to `intent_routing` (nice follow-up; the slim schema is forward-compatible).
- Multi-tenant intent mappings (requires schema migration; separate ticket).
- Full RLS audit beyond the six models already listed in `tenant_filters.py`.

## Todos

- [ ] Add `IntentCatalogItemSchema` and `GET /ai/intents` (active-only, slim payload, `get_current_user`)
- [ ] Revert admin `list_mappings` / `get_mapping` to `require_admin`; clean stale comments and unused imports
- [ ] Update frontend caller to use `GET /ai/intents`
- [ ] Remove `session.commit` in `request_lifecycle_repository`; add `flush` + docstring
- [ ] Fix `init-platform-db.sql` line 116: `'cloud'` -> `'on-prem'` for DeepSeekCoder
- [ ] Hoist imports in `tenant_filters.py`; cache `scoped` tuple
- [ ] Add `TenantContextMiddleware`, register in `main.py`, sync with `get_db_with_user`
- [ ] Sanitize `SecurityViolationError` response; log patterns server-side
- [ ] Add `gateway_verify_signature` using `hmac.compare_digest`
- [ ] Add unit tests for the above and run `ruff` / `mypy`
