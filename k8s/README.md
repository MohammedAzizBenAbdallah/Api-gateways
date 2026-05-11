# Enterprise AI Gateway — Kubernetes Deployment Guide

> **Production-grade, multi-namespace Kubernetes deployment of the Enterprise AI Gateway Orchestrator.**

---

## Architecture Overview

```
Internet
   │
   ▼
LoadBalancer Service (port 80/443)
   │
   ▼
┌─────────────────── Namespace: ai-gateway ───────────────────────┐
│  Kong Data Plane (3 pods, autoscales to 10)                     │
│  → Validates JWT, Rate Limits, Routes traffic                   │
│  Kong Control Plane (1 pod, internal Admin API only)            │
│  Frontend (2 pods)                                              │
└─────────────────────────────┬───────────────────────────────────┘
                              │
                              ▼
┌─────────────────── Namespace: ai-application ───────────────────┐
│  FastAPI Backend (3 pods, autoscales to 10)                     │
│  OPA Policy Engine (2 pods)                                     │
│  Keycloak Identity Provider (1 pod)                             │
│  Kong Logger (1 pod)                                            │
└─────────────────────────────┬───────────────────────────────────┘
                              │
                              ▼
┌─────────────────── Namespace: ai-data ──────────────────────────┐
│  PostgreSQL — Platform DB   (data: tenants, requests, events)   │
│  PostgreSQL — Kong DB       (data: routes, plugins, config)     │
│  PostgreSQL — Keycloak DB   (data: users, realms, sessions)     │
│  Redis                      (data: token quota counters)        │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────── Namespace: ai-monitoring ────────────────────┐
│  Prometheus  (metrics collection, 15-day retention)             │
│  Grafana     (dashboards, accessible via port-forward)          │
│  Alertmanager (notifications)                                   │
└─────────────────────────────────────────────────────────────────┘
```

---

## Prerequisites

| Requirement | Version | Check |
|---|---|---|
| Docker Desktop | Latest | `docker --version` |
| Kubernetes enabled | — | Docker Desktop → Settings → Kubernetes |
| kubectl | v1.28+ | `kubectl version --client` |
| make | Any | `make --version` |

**Enable Kubernetes in Docker Desktop:**
1. Open Docker Desktop
2. Settings → Kubernetes
3. Check "Enable Kubernetes"
4. Click "Apply & Restart"
5. Wait 2-3 minutes

---

## Quick Start — Deploy Everything

```bash
# 1. Verify Kubernetes is running
kubectl cluster-info

# 2. Deploy the entire platform (one command)
#    deploy.ps1 now runs preflight checks and builds local images
.\deploy.ps1

# Alternative (GNU make)
make preflight
make build-local-images
make deploy

# 3. Check everything is healthy
make status
```

---

## What Gets Deployed

| File | Namespace | Creates |
|---|---|---|
| `namespaces.yaml` | — | 4 isolated namespaces |
| `secrets/secrets.yaml` | all | All credentials (base64) |
| `data/postgres-platform.yaml` | ai-data | Platform DB + PVC |
| `data/databases.yaml` | ai-data | Kong DB + Keycloak DB + Redis |
| `application/opa.yaml` | ai-application | OPA (2 replicas) + Rego policy |
| `application/fastapi.yaml` | ai-application | FastAPI (3 replicas) + HPA |
| `application/intent-classifier.yaml` | ai-application | Intent classifier (2 replicas + HPA) + taxonomy ConfigMap |
| `application/keycloak-and-logger.yaml` | ai-application | Keycloak + Kong Logger |
| `gateway/kong-cp.yaml` | ai-gateway | Kong Control Plane |
| `gateway/kong-dp.yaml` | ai-gateway | Kong Data Plane (3 replicas) + HPA |
| `frontend-and-monitoring.yaml` | ai-gateway / ai-monitoring | Frontend + Prometheus + Grafana |
| `network-policies.yaml` | all | Zero-trust firewall rules |

---

## Useful Commands

```bash
# Run deployment preflight checks only
make preflight

# Build images required by imagePullPolicy: Never
make build-local-images

# Deploy
make deploy

# Check system status
make status

# Stream logs
make logs          # FastAPI
make logs-kong     # Kong Data Plane
make logs-opa      # OPA Policy Engine

# Access admin tools (opens browser-accessible tunnel)
make admin         # Kong Admin API → http://localhost:8001
make grafana       # Grafana → http://localhost:3001
make prometheus    # Prometheus → http://localhost:9090

# Restart services (zero downtime)
make restart-fastapi
make restart-kong

# Check autoscaling
make hpa

# Remove everything
make teardown
```

Keycloak login for the app now goes through Kong at `http://localhost/auth` (no direct `localhost:8080` port-forward required for normal app auth flow).  
If you need direct Keycloak admin/service access, use:

```bash
kubectl port-forward -n ai-application svc/keycloak 8080:8080
```

---

## TLS Model (Current)

There are two TLS layers in this deployment:

1. **Internal Kong CP↔DP mTLS (implemented and required)**
   - Kong Control Plane (`kong-cp`) and Data Plane (`kong-dp`) use the `kong-cluster-certs` secret.
   - Cert/key are mounted as `/certs/cluster.crt` and `/certs/cluster.key`.
   - `deploy.ps1` auto-generates this secret if it does not exist.
   - This secures the hybrid synchronization channel on ports `8005/8006`.

2. **External client HTTPS (environment-dependent)**
   - `kong-dp` listens on `8000` (HTTP) and `8443` (HTTPS) and is exposed as service ports `80/443`.
   - In Docker Desktop local mode, traffic can use the `LoadBalancer` localhost endpoint, but certificate trust is not automatically production-grade.
   - For cloud production, terminate TLS with Ingress + managed certificates.

---

## TLS Hardening Guidance

- Keep **cluster mTLS certificates** separate from any **edge/public certificates**.
- Rotate `kong-cluster-certs` on a schedule instead of one-time generation only.
- Do not reuse CP/DP cluster certs for browser-facing HTTPS.
- For production, use an ingress controller and automated cert issuance/renewal (for example cert-manager or cloud-native certificate integration).
- Example manifests:
  - `k8s/edge-tls-local-secret.example.yaml` (local development secret template)
  - `k8s/edge-tls-production-ingress.example.yaml` (Ingress + cert-manager pattern)

---

## Common Local Issues

| Symptom | Likely Cause | Fix |
|---|---|---|
| `ImagePullBackOff` on custom services | Local images not built | Run `make build-local-images` or `./deploy.ps1` |
| HPA shows metric errors | `metrics-server` API missing on local cluster | Safe to ignore locally, or install metrics-server |
| Keycloak/Kong Logger restart during first minutes | Slow startup / probe timing | Wait for startup probes and recheck `kubectl get pods -A` |
| HTTPS works but browser warns about cert trust | Local/self-signed edge cert behavior | Use HTTP locally or install trusted local cert chain |

---

## Network Security Model

All namespaces use **default-deny-all** NetworkPolicies.
Only these connections are explicitly allowed:

| From | To | Port | Why |
|---|---|---|---|
| `kong-dp` | `fastapi` | 3000 | AI request routing |
| `kong-dp` | `kong-logger` | 9999 | Access log shipping |
| `fastapi` | `opa` | 8181 | Policy evaluation |
| `fastapi` | `platform-db` | 5432 | Data persistence |
| `fastapi` | `redis` | 6379 | Token quota counters |
| `kong-cp` | `kong-db` | 5432 | Gateway config storage |
| `keycloak` | `keycloak-db` | 5432 | Identity data |
| `kong-logger` | `platform-db` | 5432 | Log archiving |
| `prometheus` | `fastapi` | 3000 | Metrics scraping |
| `prometheus` | `kong-dp` | 8100 | Kong metrics |

**Any other connection is silently dropped at the kernel level.**

---

## Autoscaling Behavior

| Service | Min | Max | Scale Trigger |
|---|---|---|---|
| `fastapi` | 3 | 10 | CPU > 70% OR Memory > 80% |
| `kong-dp` | 3 | 10 | CPU > 60% |

---

## Production Migration Checklist (AWS EKS)

- [ ] Replace `imagePullPolicy: Never` with `imagePullPolicy: Always`
- [ ] Push images to AWS ECR instead of local Docker
- [ ] Replace `secrets/secrets.yaml` with AWS Secrets Manager + External Secrets Operator
- [ ] Replace `PersistentVolumeClaim` with AWS EBS `StorageClass: gp3`
- [ ] Replace `LoadBalancer` service with AWS ALB Ingress Controller
- [ ] Enable `Multi-AZ` on all RDS instances
- [ ] Replace `emptyDir` cert volumes with real mTLS certificates from AWS ACM
- [ ] Configure `CloudWatch` as additional log sink for kong-logger
- [ ] Enable `Pod Disruption Budgets` for databases

---

## File Structure

```
k8s/
├── kustomization.yaml              ← Entry point: deploy everything
├── namespaces.yaml                 ← 4 isolated namespaces
├── network-policies.yaml           ← Zero-trust firewall rules
├── frontend-and-monitoring.yaml    ← Frontend, Prometheus, Grafana
├── secrets/
│   └── secrets.yaml               ← All credentials (base64)
├── data/
│   ├── postgres-platform.yaml     ← Platform DB
│   └── databases.yaml             ← Kong DB + Keycloak DB + Redis
├── application/
│   ├── opa.yaml                   ← Policy engine (2 replicas)
│   ├── intent-classifier.yaml     ← Zero-shot intent service (2 replicas + HPA)
│   ├── fastapi.yaml               ← AI backend (3 replicas + HPA)
│   └── keycloak-and-logger.yaml   ← Identity + log receiver
└── gateway/
    ├── kong-cp.yaml               ← Control Plane (1 replica)
    └── kong-dp.yaml               ← Data Plane (3 replicas + HPA)
```
