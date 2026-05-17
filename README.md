# Enterprise AI Orchestration Platform

This project is a full-stack Enterprise AI Orchestration Platform designed with a focus on security, scalability, and multi-tenancy. It integrates a Kong API Gateway, ModSecurity WAF, Keycloak for IAM, and a FastAPI backend to orchestrate AI services.

## Architecture Overview

The platform consists of several interconnected services working together to provide a secure and robust AI orchestration environment.

| Service | Port | Description |
| :--- | :--- | :--- |
| **Kong Data Plane** (`kong-dp`) | 8000, 8443, 8100 | Public-facing proxy. Serves all traffic; status/metrics on 8100. |
| **Kong Control Plane** (`kong-cp`) | _internal only_ (8001/8002/8005/8006) | DB-backed admin / Admin GUI / cluster endpoints. **Not bound to a host port** for security. Reachable only from inside the docker network (e.g. via `deck` or the FastAPI admin pod). |
| **ModSecurity WAF** | 8081 | Web Application Firewall in front of `kong-dp`. |
| **Keycloak** | 8080 | Identity and Access Management (IAM) for authentication and RBAC. |
| **FastAPI Backend** | 3000 | Core business logic and AI orchestration service. |
| **Intent Classifier** | 3010 | HuggingFace zero-shot intent labels + Redis cache (`docker compose` service `intent-classifier`). |
| **React Frontend** | 5173 *(Vite dev)* / **80** *(K8s nginx, behind Kong)* | See [k8s/README.md](k8s/README.md): use **http://localhost** through the Kong LoadBalancer for login; `5173` is only a dev/port-forward shortcut. |
| **Ollama (host)** | 11434 | Local LLM runner (running on the host machine). |
| **Hello World** | 8003 | Node.js test service for validation. |
| **Kong Logger** | 9999 | Node.js receiver that turns Kong `http-log` payloads into AWS API Gateway-style access logs and persists them to JSONL + Postgres. |
| **Platform DB** | 5433 | PostgreSQL database for permissions, orchestration, and `api_usage_records` (billing). |

### Kong hybrid topology

Kong runs in **hybrid mode**: a private control plane (`kong-cp`) owns the database, Admin API, and Admin GUI; one or more data planes (`kong-dp`) pull config from it over an mTLS cluster channel and serve all proxy traffic. The cluster certificate is generated once on first startup by the `kong-cluster-cert-gen` one-shot service into a named volume (`kong_cluster_certs`) and shared between CP and DP.

```text
                 +-------------------+        mTLS 8005/8006
 internet --->   |  kong-dp (public) |  <----------------------  kong-cp (private)
                 |  8000/8443/8100   |                            8001/8002 (no host port)
                 +-------------------+                                  |
                          |                                           kong-db
                       upstreams
```

To reach the Admin API for ad-hoc operations, exec into a container on the same docker network, e.g.:

```bash
docker compose exec deck curl -s http://kong-cp:8001/status
```

### AWS API Gateway-style access logs

Every request handled by `kong-dp` is logged as a single JSON record shaped like an AWS API Gateway access log (fields: `requestId`, `apiId`, `stage`, `httpMethod`, `resourcePath`, `status`, `responseLatency`, `identity.*`, `authorizer.claims.*`, `integration.*`, `error.*`, `waf.action`, plus a `billing` block with `requests`, `dataProcessedBytes`, `cacheHit`).

Records land in two sinks:

- **`kong-logger/logs/access-YYYYMMDD.jsonl`** — daily-rotated JSONL archive on disk.
- **`platform-db.api_usage_records`** — queryable Postgres table indexed on `(api_id, request_time)`, `(consumer_id, request_time)`, and `request_id`. A convenience view `api_usage_hourly` aggregates request counts and bytes per consumer/api/hour, ready to feed a metered-billing pipeline.

## Prerequisites

Before starting, ensure you have the following installed on your machine:
- **Docker + Docker Compose**
- **Ollama** installed on the host machine
- **Node.js 18+**
- **Python 3.11+**

## Quick Start

1. **Clone the repository**:
   ```bash
   git clone <your-repo-url>
   cd apiGatewayDemo
   ```

2. **Setup environment variables**:
   Copy the example environment files and fill in the required values (passwords, secrets, etc.).
   ```bash
   cp .env.example .env
   cp fastapi_backend/.env.example fastapi_backend/.env
   cp frontend/.env.example frontend/.env
   cp kong-logger/.env.example kong-logger/.env
   ```

3. **Pull required AI models**:
   ```bash
   ollama pull llama3.2
   ollama pull deepseek-coder
   ```

4. **Launch the platform**:
   ```bash
   docker compose up -d
   ```

5. **Access the application** (Docker Compose defaults):
   - Frontend: [http://localhost:5173](http://localhost:5173)
   - Keycloak Admin: [http://localhost:8080](http://localhost:8080)
   - Kong Manager: [http://localhost:8002](http://localhost:8002)

### Kubernetes (alternative)

For the full enterprise stack on Kubernetes, use **`deploy.ps1`** (Windows) or **`make deploy`** — see [k8s/README.md](k8s/README.md). **Run `deploy.ps1` as Administrator on first setup** so it can set machine-level `OLLAMA_KEEP_ALIVE=-1` (keeps host Ollama models loaded for low first-token latency). In that layout:

- End users open the app at **http://localhost** (Kong `LoadBalancer` → frontend on **port 80**, not Vite 5173).
- OAuth / Keycloak discovery for the SPA is **http://localhost/auth** (routed by Kong), not direct `localhost:8080` in the browser.
- Direct Keycloak admin still uses **port-forward**: `kubectl port-forward -n ai-application svc/keycloak 8080:8080`.

## Security Architecture

The platform implements a multi-layered security strategy to ensure defense-in-depth:
**WAF** (ModSecurity) → **Kong TLS** → **Rate Limiting** → **JWT/Keycloak** → **RBAC** → **FastAPI tenant isolation** → **Audit logging**.

Requests are first inspected by the WAF for common exploits, then routed through Kong with TLS encryption. Authentication is handled by Keycloak, and Kong enforces JWT validation and rate limits. The backend provides further isolation between tenants and logs all critical actions to the dedicated logging service.

## Project Structure

```text
/
├── gateway/              # Kong configuration and custom Lua plugins
├── waf/                  # ModSecurity exclusion rules and audit logs
├── keycloak/             # Realm export and IAM configuration
├── fastapi_backend/      # Python FastAPI application (Core Logic)
├── frontend/             # React (Vite) frontend application
├── hello_world/          # Node.js test service
├── kong-logger/          # Node.js log server for audit trails
├── backend/scripts/      # PostgreSQL initialization scripts
├── docker-compose.yml    # Main orchestration file
├── k8s/                  # Kubernetes manifests (see k8s/README.md)
└── .env.example          # Template for environment variables
```

## Default Credentials (Development Only)
- **Kong DB**: `kong`/`kong`
- **Keycloak DB**: `keycloak`/`password`
- **Platform DB**: `platform_admin`/`platform_pass`
- **Keycloak Admin**: `admin`/`admin`
