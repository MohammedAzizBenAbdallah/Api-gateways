# Backlog Audit Report

## GitHub Sync Decision

- Local branch: `main`
- After `git fetch origin`, `HEAD`, `origin/main`, and remote `main` all resolve to `32f75f679595355533869027d3e5534d6194fbe6`.
- Working tree has local uncommitted changes, but branch is not behind remote.
- Decision: no `pull`/`merge` needed before proceeding.

## Status Legend

- `finished`: implemented end-to-end in current codebase
- `partially finished`: implemented in part, with notable gaps
- `not finished yet`: missing or only config placeholders

## Task-by-Task Classification

### Sprint 1

- `ORK-001` `partially finished` - Kong gateway is configured, but declarative/runtime plugin drift remains (`docker-compose.yml`, `gateway/kong_final.yaml`).
- `ORK-002` `partially finished` - TLS listeners and certs exist, but strict redirect/protocol coverage is incomplete (`gateway/kong_final.yaml`).
- `ORK-003` `partially finished` - rate-limit evidence exists in exported plugin snapshots, not fully in current declarative source (`all_plugins.json`, `gateway/kong_final.yaml`).
- `ORK-004` `partially finished` - ModSecurity + CRS deployed but ingress path consistency determines enforcement (`docker-compose.yml`, `waf/exclusions.conf`).
- `ORK-005` `finished` - `/api` route carries request-size-limiting, ip-restriction, gateway-signature, and http-log in declarative Kong config (`gateway/kong_final.yaml`).
- `ORK-006` `finished` - Kong http-log sink writes one normalized JSON line per request (`kong-logger/server.js`, `gateway/kong_final.yaml`).

### Sprint 2

- `ORK-007` `finished` - JWT validation middleware is implemented (`fastapi_backend/app/core/security.py`).
- `ORK-008` `finished` - SPA client `myclient` uses explicit redirect/web origins; confidential `orchestrator-service` added for M2M (`keycloak/realm-export.json`).
- `ORK-009` `finished` - `SERVICE_ACCOUNT_TENANT_MAP` maps `azp` client id to `tenant_id`; Keycloak client `orchestrator-service` with service account (`fastapi_backend/app/core/config.py`, `fastapi_backend/app/core/security.py`, `keycloak/realm-export.json`).
- `ORK-010` `finished` - tenant claim is consumed in request context and enforced in orchestration (`fastapi_backend/app/core/security.py`, `fastapi_backend/app/services/ai_request_service.py`).
- `ORK-011` `partially finished` - cross-tenant blocking exists (permission checks + RLS), but management and full boundary coverage are incomplete (`fastapi_backend/app/repositories/permission_repository.py`, `backend/scripts/init-platform-db.sql`).

### Sprint 3

- `ORK-012` `finished` - `POST /api/ai/request` exists with stream/JSON paths (`fastapi_backend/app/api/ai.py`).
- `ORK-013` `finished` - strict schema validation with typed payload/metadata is present (`fastapi_backend/app/schemas/ai_request.py`).
- `ORK-014` `finished` - request metadata persistence to Postgres is implemented (`fastapi_backend/app/repositories/ai_request_repository.py`).
- `ORK-015` `finished` - `taxonomy.yaml` loaded at startup; unknown intents rejected; admin mappings stamped with taxonomy version (`fastapi_backend/app/services/taxonomy_service.py`, `fastapi_backend/app/main.py`, `fastapi_backend/app/services/intent_mappings_service.py`).
- `ORK-016` `not finished yet` - no intent classifier microservice/model was found; intent is client-provided (`fastapi_backend/app/services/ai_request_service.py`).
- `ORK-017` `finished` - intent-to-service mappings are persisted and cached (`fastapi_backend/app/models/intent_routing.py`, `fastapi_backend/app/services/intent_mappings_service.py`).
- `ORK-018` `finished` - payload/content inspector exists and feeds sensitivity decisions (`fastapi_backend/app/services/content_inspector_service.py`).

### Sprint 4

- `ORK-019` `finished` - routing map behavior exists through deterministic intent resolution (`fastapi_backend/app/services/intent_cache_service.py`).
- `ORK-020` `finished` - no-fallback behavior is enforced (unresolvable mappings are rejected) (`fastapi_backend/app/services/intent_cache_service.py`).
- `ORK-021` `finished` - routing/policy decisions are persisted in audit tables (`fastapi_backend/app/repositories/policy_audit_repository.py`).
- `ORK-022` `finished` - execution proxy/orchestration handler is implemented in service layer (`fastapi_backend/app/services/ai_request_service.py`).
- `ORK-023` `finished` - non-stream responses validated with `OllamaProviderEnvelope` before return (`fastapi_backend/app/schemas/provider_ollama.py`, `fastapi_backend/app/services/ai_request_service.py`).
- `ORK-024` `finished` - append-only `request_lifecycle_events` written at key stages (`fastapi_backend/app/repositories/request_lifecycle_repository.py`, `fastapi_backend/app/services/ai_request_service.py`).
- `ORK-025` `finished` - Kong `gateway-signature` HMAC + Redis nonce replay guard in FastAPI (`gateway/plugins/gateway-signature`, `fastapi_backend/app/core/gateway_signature.py`, `fastapi_backend/app/core/middleware.py`).
- `ORK-026` `finished` - AI service registry CRUD API exists (`fastapi_backend/app/api/admin/services.py`).

### Sprint 5

- `ORK-027` `finished` - policy schema/DSL and loading workflow exist (`fastapi_backend/app/schemas/policy.py`, `fastapi_backend/app/services/policy_service.py`).
- `ORK-028` `finished` - OPA sidecar in Compose; `PolicyService.evaluate_async` POSTs to `/v1/data/orchestrator` with fail-open fallback (`docker-compose.yml`, `opa/policies/orchestrator.rego`, `fastapi_backend/app/services/policy_service.py`).
- `ORK-029` `finished` - sensitivity-driven governance enforcement is implemented (`fastapi_backend/app/services/ai_request_service.py`, `fastapi_backend/app/services/policy_service.py`).
- `ORK-030` `finished` - per-request token usage logging exists (`fastapi_backend/app/repositories/usage_repository.py`).
- `ORK-031` `finished` - per-tenant Redis quotas exist (`fastapi_backend/app/services/quota_service.py`, `fastapi_backend/quotas.yaml`).
- `ORK-032` `finished` - over-quota requests are rejected before provider execution (`fastapi_backend/app/services/ai_request_service.py`).
- `ORK-033` `partially finished` - environment fields and controls exist, but strict cross-environment isolation is incomplete (`fastapi_backend/app/schemas/ai_request.py`, `fastapi_backend/app/services/policy_service.py`).

### Sprint 6

- `ORK-034` `finished` - PostgreSQL RLS is implemented in DB bootstrap SQL (`backend/scripts/init-platform-db.sql`).
- `ORK-035` `finished` - SQLAlchemy ORM execute hook scopes tenant models via `ContextVar`; admin path preserved (`fastapi_backend/app/infrastructure/db/tenant_filters.py`, `fastapi_backend/app/infrastructure/db/session.py`).
- `ORK-036` `not finished yet` - Vault runtime integration for secret retrieval/storage is not present in backend services (`vault/vault-config.hcl`, `fastapi_backend/app`).
- `ORK-037` `partially finished` - some least-privilege concepts exist (RLS/session vars), but service-specific DB role hardening is incomplete (`backend/scripts/init-platform-db.sql`).
- `ORK-038` `not finished yet` - no automated secrets rotation flow found in app/runtime code.

### Sprint 7

- `ORK-039` `finished` - prompt injection scanning middleware/service is implemented (`fastapi_backend/app/services/prompt_security_service.py`).
- `ORK-040` `finished` - per-tenant Redis block threshold and richer `metadata_extra` on security events from scan metadata (`fastapi_backend/app/services/prompt_security_service.py`, `fastapi_backend/app/services/ai_request_service.py`).
- `ORK-041` `finished` - blocked prompt events are logged as security events (`fastapi_backend/app/repositories/security_event_repository.py`, `fastapi_backend/app/services/ai_request_service.py`).
- `ORK-042` `not finished yet` - strict per-service JSON schema validation of AI outputs before returning is not implemented.
- `ORK-043` `finished` - PII redaction in outputs is implemented (`fastapi_backend/app/services/output_guard_service.py`).
- `ORK-044` `not finished yet` - hallucination anomaly guard/risk scoring is not present.

### Sprint 8

- `ORK-045` `finished` - Prometheus instrumentation is active (`fastapi_backend/app/main.py`, `monitoring/prometheus.yml`).
- `ORK-046` `partially finished` - Grafana stack exists, but dashboard provisioning is not fully implemented in repo (`docker-compose.yml`).
- `ORK-047` `partially finished` - audit logging exists but not as a proven immutable append-only lifecycle trail for all stages (`fastapi_backend/app/repositories/ai_request_repository.py`, `fastapi_backend/app/repositories/policy_audit_repository.py`).
- `ORK-048` `partially finished` - token usage aggregation is partially exposed through admin metrics, but complete API+dashboard objective is not fully done (`fastapi_backend/app/api/admin/metrics.py`, `frontend/src/components/AdminPortal.jsx`).
- `ORK-049` `partially finished` - unit tests plus OPA path covered with `respx`; full stack integration coverage still limited (`fastapi_backend/tests/unit/test_policy_opa_respx.py`, `fastapi_backend/tests/integration`).
- `ORK-050` `not finished yet` - no Locust scenarios/results found in repo.
- `ORK-051` `not finished yet` - no OWASP ZAP run artifacts/reporting flow found in repo.
- `ORK-052` `not finished yet` - go-live readiness checklist/sign-off artifact not found.

## Current Totals

- `finished`: 33
- `partially finished`: 11
- `not finished yet`: 8
