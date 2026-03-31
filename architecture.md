## 1. Current Project Structure (`fastapi_backend/`)

```text
fastapi_backend/
  venv/
  .env
  .env.example
  Dockerfile
  __init__.py
  auth.py
  config.py
  database.py
  main.py
  middleware.py
  models.py
  requirements.txt
  taxonomy.yaml
  test_content_inspector.py
  token.json
migrations/
  create_intent_routing.sql
  migrate_taxonomy.py
routers/
  admin_intent_mappings.py
  __pycache__/
    admin_intent_mappings.cpython-311.pyc
routes/
  __init__.py
  admin.py
  ai.py
  __pycache__/
    __init__.cpython-311.pyc
    __init__.cpython-313.pyc
    ai.cpython-311.pyc
    ai.cpython-313.pyc
schemas/
  intent_mapping.py
  __pycache__/
    intent_mapping.cpython-311.pyc
services/
  content_inspector.py
  intent_cache.py
  __pycache__/
    content_inspector.cpython-311.pyc
    intent_cache.cpython-311.pyc
__pycache__/
  auth.cpython-311.pyc
  auth.cpython-313.pyc
  config.cpython-311.pyc
  config.cpython-313.pyc
  database.cpython-311.pyc
  database.cpython-313.pyc
  main.cpython-311.pyc
  main.cpython-313.pyc
  middleware.cpython-311.pyc
  middleware.cpython-313.pyc
  models.cpython-311.pyc
  models.cpython-313.pyc
```

Notes:
- I’m **excluding `venv/` contents** from responsibility-level analysis.
- `routes/admin.py` exists but is **empty**.

---

## 2. Architecture Pattern Assessment

This is best described as a **router-centric modular monolith** that *tries* to be layered (there are `services/`, `schemas/`, and `models/` directories), but in practice it behaves like **fat routers**: `fastapi_backend/routes/ai.py` and `fastapi_backend/routers/admin_intent_mappings.py` contain orchestration, authorization/auditing, persistence, and external-provider calling all in one place. “Services” also aren’t fully framework-agnostic: `fastapi_backend/services/intent_cache.py` raises `fastapi.HTTPException`, creating a **presentation/framework dependency inside business logic**. Overall: **inconsistent layering**, closer to “vertical slice / fat-handler” than clean or hexagonal architecture.

---

## 3. File-by-File Responsibility Breakdown (first-party, excluding `__pycache__/` and `venv/`)

### `fastapi_backend/main.py`
- **What it does:** Creates the `FastAPI` app, configures CORS, defines health endpoints, loads spaCy in lifespan, initializes `intent_cache`, and includes routers.
- **Layer:** Mixed **infrastructure + presentation composition**.
- **Scope correctness:** Startup concerns (spaCy loading, intent cache init) are reasonable, but `main.py` also owns app-level routing composition *and* mock endpoints (`/api/documents`, `/api/admin`), which suggests environment-/example behavior is intertwined with the core service.

Key evidence:
- spaCy load + error handling in `lifespan()` (lines 17–34)
- CORS policy (lines 42–48)
- mocked endpoints (lines 61–86)
- router composition (lines 88–89)

---

### `fastapi_backend/routes/ai.py`
- **What it does:** Defines the `/ai/request` endpoint with both SSE streaming and JSON fallback. It also contains:
  - tenant authorization + permission auditing (`authorize_tenant_service`)
  - request lifecycle tracking (`_update_request_status`) and SSE generator (`_sse_generator`)
  - content inspection (`inspect_content(...)` using `request.app.state.nlp`)
  - external AI provider call via `httpx`
  - persistence updates across the flow (received → streaming/completed/failed)
- **Layer:** Currently **presentation + business logic + infrastructure + persistence + streaming protocol** all mixed.
- **Scope correctness:** Responsibilities are significantly **over-scoped** for a router module; this is the main architectural hotspot.

Key evidence:
- Schemas/enums live in the router (lines 35–62)
- Auth/auditing helper does DB + commits (lines 68–102)
- Tracking persistence helper uses independent session (lines 109–133)
- SSE generator streams and also writes tracking state (lines 139–203)
- Endpoint orchestration includes DB writes, content inspection, provider calling, and response shaping (lines 211–380)

---

### `fastapi_backend/routes/admin.py`
- **What it does:** Nothing (empty file).
- **Layer:** None / dead placeholder.
- **Scope correctness:** Naming implies it should host admin endpoints, but it’s unused (and actual admin intent mapping endpoints are in `routers/admin_intent_mappings.py`).

---

### `fastapi_backend/routers/admin_intent_mappings.py`
- **What it does:** Admin endpoints for intent routing mappings:
  - role enforcement (`require_admin`)
  - CRUD over `IntentRouting` rows
  - audit log writes (`IntentMappingAuditLog`)
  - soft delete (`is_active = False`)
  - admin-triggered cache reload (`intent_cache.force_reload()`)
- **Layer:** Mixed **presentation + orchestration + persistence**.
- **Scope correctness:** The router performs direct DB operations and audit writes; there’s no repository/service boundary separating those responsibilities.

Key evidence:
- Role check (lines 16–21)
- Direct selects/updates and commits across endpoints (e.g., create at lines 43–73, update at 80–114, delete at 116–143)
- Cache reload trigger (lines 145–149)

---

### `fastapi_backend/services/content_inspector.py`
- **What it does:** Synchronous PII/sensitivity inspector:
  - runs spaCy NER over combined message text
  - runs an email regex scan
  - upgrades sensitivity to HIGH if PII is found
- **Layer:** **Business logic** (domain policy).
- **Scope correctness:** Relatively well-scoped. It doesn’t depend on FastAPI and keeps spaCy loading external (passed via `nlp`).

Key evidence:
- `SensitivityLevel` and PII detection (lines 34–48)
- `inspect(...)` returns `SensitivityLevel` and is synchronous (lines 55–129)

---

### `fastapi_backend/services/intent_cache.py`
- **What it does:** In-memory cache mapping `intent_name -> service_id` with DB-backed initialization and periodic background refresh.
- **Layer:** Business logic + data access + scheduling (but framework coupled).
- **Scope correctness:** It performs DB access directly (via `AsyncSessionLocal`) and is not framework-agnostic because it raises `HTTPException` when an intent is missing.

Key evidence:
- DB load and cache build inside `force_reload()` (lines 27–46)
- Background refresh loop (lines 54–59)
- Raises `HTTPException` from inside service logic (lines 67–71)

---

### `fastapi_backend/schemas/intent_mapping.py`
- **What it does:** Pydantic models for request/response payloads for intent mapping.
- **Layer:** **Schemas / data contracts**.
- **Scope correctness:** Properly scoped.

Key evidence:
- Base/create/update/response models (lines 6–27)

---

### `fastapi_backend/models.py`
- **What it does:** SQLAlchemy ORM models for:
  - `AIService`
  - `TenantServicePermission`
  - `PermissionAuditLog`
  - `IntentRouting`
  - `IntentMappingAuditLog`
  - `AIRequestRecord`
- **Layer:** **Data access / persistence models**.
- **Scope correctness:** Mostly fine; plain ORM entities without business logic.

Key evidence:
- `AIRequestRecord` tracks request status/sensitivity lifecycle (lines 62–76)

---

### `fastapi_backend/config.py`
- **What it does:** Loads env vars (via `load_dotenv()`) and defines configuration constants.
- **Layer:** **Configuration core**.
- **Scope correctness:** Works, but the import-time dotenv loading is a configuration management smell (makes runtime behavior depend on working directory and import timing).

Key evidence:
- `load_dotenv()` at import time (line 6)
- env var mapping (lines 12–16)

---

### `fastapi_backend/auth.py`
- **What it does:** Verifies Keycloak JWTs using JWKS fetched over HTTP, caches JWKS in memory, decodes token, manually checks issuer, and returns JWT payload claims.
- **Layer:** **Security / infrastructure**.
- **Scope correctness:** Functionally plausible, but there are architecture and security-quality issues:
  - JWKS caching is global and not concurrency-safe
  - no explicit refresh/expiration policy
  - broad exception handling with `print`

Key evidence:
- Global `jwks_cache` (lines 9–11)
- JWKS fetch and cache set (lines 12–25)
- issuer allowlist logic + token decode (lines 50–66)
- broad exception -> reset cache -> HTTPException (lines 69–76)

---

### `fastapi_backend/middleware.py`
- **What it does:** Enforces the presence of a `kong-header` header for requests.
- **Layer:** **Middleware / request boundary**.
- **Scope correctness:** There is duplicated logic:
  - `kong_header_middleware(...)` exists but is not used
  - `verify_kong_header(...)` duplicates the header check and is used as a dependency

Key evidence:
- `kong_header_middleware` (lines 3–10)
- `verify_kong_header` (lines 12–18)

---

### `fastapi_backend/database.py`
- **What it does:** Creates async SQLAlchemy engine + session factory and exposes `get_db()` dependency.
- **Layer:** **Infrastructure / persistence setup**.
- **Scope correctness:** Acceptable, but:
  - `engine` is created at import time
  - `echo=True` always enables verbose SQL logging
  - it doesn’t guard against `DATABASE_URL` being unset

Key evidence:
- `echo=True` (line 11)
- `get_db()` yields session (lines 15–18)

---

### `fastapi_backend/migrations/migrate_taxonomy.py`
- **What it does:** Script that reads `taxonomy.yaml` and upserts `IntentRouting` using PostgreSQL `INSERT ... ON CONFLICT`.
- **Layer:** **Infrastructure / migrations**.
- **Scope correctness:** It’s a one-off migration script, which is fine, but it’s still tightly coupled to ORM + session factory.

Key evidence:
- `TAXONOMY_PATH` resolution (line 10)
- upsert loop and conflict update (lines 25–43)

---

### `fastapi_backend/taxonomy.yaml`
- **What it does:** Declarative list of intents and their `service_id` plus examples.
- **Layer:** **Domain configuration data**.
- **Scope correctness:** Fine.

Key evidence:
- `version` and `intents` structure (lines 1–28)

---

### `fastapi_backend/migrations/create_intent_routing.sql`
- **What it does:** SQL schema for `intent_routing` + `intent_mapping_audit_logs` tables and triggers.
- **Layer:** **Infrastructure / migrations**.
- **Scope correctness:** Fine as raw migration SQL.

Key evidence:
- table definitions and updated_at trigger (lines 4–45)

---

### `fastapi_backend/test_content_inspector.py`
- **What it does:** An integration-ish script:
  - calls the running API endpoint over HTTP
  - uses a **hardcoded bearer token**
  - uses `docker exec` to query DB directly for assertion-like output
- **Layer:** **Testing (but not unit-tested) / operational script**.
- **Scope correctness:** Not a true unit test suite; mixes network + Docker + hardcoded secrets.

Key evidence:
- hardcoded `TOKEN` constant (line 5)
- calls endpoint on `localhost:8000/api/ai/request` (lines 8–14)
- uses `docker exec ... psql ...` for DB inspection (lines 47–55)

---

### `fastapi_backend/Dockerfile`
- **What it does:** Builds the backend image, installs deps, downloads spaCy model at build time, and runs `uvicorn`.
- **Layer:** **Infrastructure / deployment**.
- **Scope correctness:** Acceptable.

Key evidence:
- `python -m spacy download en_core_web_sm` (line 13)
- `CMD ["uvicorn", "main:app", ...]` (line 18)

---

### `fastapi_backend/requirements.txt`
- **What it does:** Declares Python dependencies.
- **Layer:** **Packaging/dependencies**.

---

### `fastapi_backend/.env.example`
- **What it does:** Example env vars.
- **Layer:** **Config**.

Key evidence:
- `PLATFORM_DB_URL`, `KEYCLOAK_URL`, `PORT`, `CORS_ORIGIN` (lines 1–6)

---

### `fastapi_backend/.env`
- **What it does:** Actual local env values including DB URL with a DB password.
- **Layer:** **Config/secrets**.
- **Scope correctness:** Not safe to commit.

Key evidence:
- `PLATFORM_DB_URL=...platform_pass...` (line 5)

---

### `fastapi_backend/token.json`
- **What it does:** Captured JWT contents (access + refresh tokens).
- **Layer:** **Security/secret material**.
- **Scope correctness:** **Not safe to commit**.

Key evidence:
- contains `access_token` and `refresh_token` fields (lines 1–6)

---

## 4. Violations and Code Smells (grouped)

### Separation of concerns violations
- `fastapi_backend/routes/ai.py` is a “god module”:
  - mixes request schemas (lines 35–62), auth/audit (68–102), DB tracking (109–133), SSE generator streaming protocol (139–203), and provider orchestration (211–380).
- `fastapi_backend/routers/admin_intent_mappings.py` mixes:
  - authorization (`require_admin`, lines 16–21),
  - persistence CRUD + audit log writes (create/update/delete blocks),
  - and cache reload orchestration (lines 145–149).
- `fastapi_backend/routes/ai.py` does DB writes from inside the SSE generator via `AsyncSessionLocal` (lines 122–129), bypassing the injected `db` session pattern used in the handler signature (lines 211–218).
- `fastapi_backend/services/intent_cache.py` mixes business logic, persistence, and scheduling (DB load in `force_reload`, background refresh loop in `_background_refresh`, lines 27–46 and 54–59).

### Dependency direction / layering violations
- Framework leak into service layer:
  - `fastapi_backend/services/intent_cache.py` raises `fastapi.HTTPException` from `resolve_intent()` (lines 67–71).
- Routers directly depend on ORM models and persistence operations instead of going through repositories/services:
  - `fastapi_backend/routes/ai.py` queries/updates ORM models inline (e.g., service lookup lines 231–239; request record create lines 243–256; completion update lines 337–343).
  - `fastapi_backend/routers/admin_intent_mappings.py` performs direct DB CRUD inline across endpoints (e.g., list at lines 23–29; create at 43–73; update at 80–114; delete at 116–143).

### Naming / structure issues
- Two competing directory conventions for routers:
  - `fastapi_backend/routes/ai.py` vs `fastapi_backend/routers/admin_intent_mappings.py`
  - plus `fastapi_backend/main.py` imports from both `routes` and `routers` (lines 10–12, 88–89).
- `fastapi_backend/routes/admin.py` exists but is empty (no responsibility), while “admin endpoints” actually live elsewhere.

### Security & configuration management issues
- Committed secrets:
  - `fastapi_backend/.env` contains a DB password inside `PLATFORM_DB_URL` (line 5).
  - `fastapi_backend/token.json` contains real-looking `access_token` and `refresh_token` fields (lines 1–6).
  - `fastapi_backend/test_content_inspector.py` hardcodes a JWT bearer token (`TOKEN` constant, line 5).
- Unsafe CORS configuration:
  - `fastapi_backend/main.py` sets `allow_origins=["*"]` while also setting `allow_credentials=True` (lines 42–48), which is both insecure and typically invalid per CORS rules.
- Import-time configuration side effects:
  - `fastapi_backend/config.py` calls `load_dotenv()` at import time (line 6), making behavior dependent on current working directory and import order.

### Duplications / type confusion
- Sensitivity enum duplication across layers:
  - `fastapi_backend/services/content_inspector.py` defines `SensitivityLevel` (lines 34–38)
  - `fastapi_backend/routes/ai.py` defines a separate `Sensitivity_level` enum (lines 35–39)
  - The endpoint then compares the resolved value to `SensitivityLevel(body.metadata.sensitivity)` (lines 268–272), which works but is confusing and invites drift.
- Kong header enforcement logic duplicated:
  - `fastapi_backend/middleware.py` has `kong_header_middleware()` (lines 3–10) and a separate `verify_kong_header()` dependency (lines 12–18) with essentially the same policy.

### Testability & lifecycle/correctness smells
- Non-test integration script:
  - `fastapi_backend/test_content_inspector.py` mixes:
    - HTTP calls to a live service,
    - hardcoded tokens,
    - and `docker exec` DB inspection (lines 47–55),
    - which makes it brittle and unsafe as part of automated CI.
- Background task lifecycle unmanaged:
  - `fastapi_backend/services/intent_cache.py` starts an infinite `_background_refresh()` loop via `asyncio.create_task(...)` (lines 20–26 and 54–59) with no explicit cancellation tied to FastAPI shutdown.
- Logging/error handling inconsistency:
  - `fastapi_backend/routes/ai.py` uses `print(...)` for tracking/SSE failures (e.g., lines 130–132, 194–196, 361–375) rather than structured logging.

---

## 5. Current Dependency Graph

```text
Client
  -> FastAPI app (fastapi_backend/main.py)
      -> routes/ai.py (AI endpoint)
          -> DB directly (via get_db + ORM selects/updates in handler)
             ↘ DB direct writes inside SSE generator via AsyncSessionLocal (violation: bypass DI)
          -> services/intent_cache.intent_cache (global singleton)
              -> DB directly (AsyncSessionLocal) (no repository)
              -> raises HTTPException (framework coupling violation)
          -> services/content_inspector (policy) with spaCy nlp from app.state
          -> auth.get_current_user (JWT verification -> Keycloak JWKS via httpx)
          -> external AI provider call via httpx
      -> routers/admin_intent_mappings.py
          -> DB directly (CRUD on IntentRouting + audit log writes)
          -> auth.get_current_user + middleware.verify_kong_header
          -> services/intent_cache.force_reload()
```

---

## 6. What a Clean Version of This Project Should Look Like

### Ideal folder structure (clean-architecture-ish)

```text
app/
  api/                # routers only (no business logic)
  services/          # orchestration + domain policy
  repositories/      # all DB access
  schemas/           # Pydantic request/response models
  core/              # config, security, middleware
  models/            # SQLAlchemy models (entities)
  infrastructure/    # external integrations (DB session, Keycloak/JWKS, spaCy loader, AI provider clients)
tests/
scripts/             # migrations / one-off scripts
```

### Mapping: current files -> where they should live
- `fastapi_backend/main.py` -> `app/main.py` (app factory + lifespan + router wiring)
- `fastapi_backend/routes/ai.py` -> `app/api/ai.py` (router only) + move schemas to `app/schemas/ai_request.py` + move orchestration to `app/services/ai_request_service.py`
- `fastapi_backend/routers/admin_intent_mappings.py` -> `app/api/admin/intent_mappings.py` (router only) + move CRUD/audit orchestration to services/repositories
- `fastapi_backend/services/intent_cache.py` -> `app/services/intent_cache.py` (framework-agnostic) + DB access to `app/repositories/intent_routing_repository.py`
- `fastapi_backend/services/content_inspector.py` -> `app/services/content_inspector.py` (domain policy) and accept injected `nlp` from `app/infrastructure/nlp/spacy_loader.py`
- `fastapi_backend/schemas/intent_mapping.py` -> `app/schemas/intent_mapping.py`
- `fastapi_backend/models.py` -> `app/models/sqlalchemy_models.py`
- `fastapi_backend/database.py` -> `app/infrastructure/db/session.py` (and repositories use injected session)
- `fastapi_backend/auth.py` -> `app/core/security/keycloak_auth.py` + JWKS HTTP client to `app/infrastructure/auth/jwks_client.py` if desired
- `fastapi_backend/middleware.py` -> `app/core/middleware.py`
- `fastapi_backend/migrations/migrate_taxonomy.py` -> `scripts/migrate_taxonomy.py` (or `app/infrastructure/migrations/`)
- `fastapi_backend/migrations/create_intent_routing.sql` -> `scripts/create_intent_routing.sql` (or migration folder)
- `fastapi_backend/taxonomy.yaml` -> `app/infrastructure/data/taxonomy.yaml` (or configuration-owned data dir)
- `fastapi_backend/test_content_inspector.py` -> `tests/` (unit/integration tests, no secrets, no docker exec)

Also:
- Remove committed secrets files (`fastapi_backend/.env`, `fastapi_backend/token.json`) from repo; keep examples only (e.g. `.env.example`) in version control.

---

## 7. Priority Refactor List (top 10, highest impact first)

1. Remove committed secrets and token material
   - Affected: `fastapi_backend/.env`, `fastapi_backend/token.json`, `fastapi_backend/test_content_inspector.py`
   - Complexity: low
2. Split `fastapi_backend/routes/ai.py` into router-only + services + repositories + schemas
   - Affected: `fastapi_backend/routes/ai.py` (major), plus new/changed modules under `services/` + `repositories/` + `schemas/`
   - Complexity: high
3. Introduce a proper repository layer for all DB operations
   - Affected: `fastapi_backend/routes/ai.py`, `fastapi_backend/routers/admin_intent_mappings.py`, `fastapi_backend/services/intent_cache.py`, `fastapi_backend/database.py`
   - Complexity: high
4. Make `services/intent_cache.py` framework-agnostic (no `HTTPException`)
   - Affected: `fastapi_backend/services/intent_cache.py`, `fastapi_backend/routes/ai.py`
   - Complexity: medium
5. Consolidate sensitivity types and schemas (remove enum duplication)
   - Affected: `fastapi_backend/services/content_inspector.py`, `fastapi_backend/routes/ai.py`
   - Complexity: low/medium
6. Standardize router naming/layout (`routes/` vs `routers/`) and remove empty placeholder `routes/admin.py`
   - Affected: `fastapi_backend/main.py`, `fastapi_backend/routes/ai.py`, `fastapi_backend/routers/admin_intent_mappings.py`, `fastapi_backend/routes/admin.py`
   - Complexity: low
7. Fix lifecycle management of `intent_cache` background refresh task
   - Affected: `fastapi_backend/main.py`, `fastapi_backend/services/intent_cache.py`
   - Complexity: medium/high
8. Remove global singleton coupling for `intent_cache` (dependency injection or app-state binding)
   - Affected: `fastapi_backend/main.py`, `fastapi_backend/services/intent_cache.py`, `fastapi_backend/routes/ai.py`, `fastapi_backend/routers/admin_intent_mappings.py`
   - Complexity: medium
9. Harden configuration (CORS correctness + config loading strategy)
   - Affected: `fastapi_backend/main.py`, `fastapi_backend/config.py`
   - Complexity: low/medium
10. Replace `test_content_inspector.py` with safe, deterministic tests
   - Affected: `fastapi_backend/test_content_inspector.py`, likely `fastapi_backend/services/content_inspector.py` (to support unit testing)
   - Complexity: medium

---

## 8. “Current Architecture Status” (README-ready, brutally honest)

This FastAPI codebase is currently a **router-centric implementation** where core business orchestration, authorization/auditing, persistence, streaming protocol handling, and external AI provider calls are concentrated inside `fastapi_backend/routes/ai.py` and admin CRUD logic lives directly inside `fastapi_backend/routers/admin_intent_mappings.py`. While there are `services/`, `schemas/`, and `models/` directories, the layering is inconsistent: `fastapi_backend/services/intent_cache.py` still raises `HTTPException` (framework coupling), DB access is performed directly from routers (no repository boundary), and configuration/security are handled in ways that reduce safety and testability (import-time dotenv loading plus committed secrets via `fastapi_backend/.env` and `fastapi_backend/token.json`, and a hardcoded JWT in `fastapi_backend/test_content_inspector.py`). The result is a system that may work in development but is hard to extend safely, difficult to unit test, and risky to operate due to security and lifecycle/coupling issues.

If you want, I can also produce a “clean target” dependency graph for the refactored architecture (router → service → repository → DB) based on the same modules.

