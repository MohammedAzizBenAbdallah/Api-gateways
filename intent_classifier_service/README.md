# Intent classifier microservice

FastAPI service that assigns **exactly one** intent label per request. It loads a taxonomy from YAML, calls **Ollama’s chat HTTP API** (JSON output) via `LLM_BASE_URL`, and caches results in **Redis** plus an **in-memory LRU**.

## API

- `POST /classify` — body `{"text": "...", "tenant_id": "optional", "environment": "optional"}`
- `GET /healthz` — process up
- `GET /readyz` — classifier wiring ready
- `GET /metrics` — Prometheus (`prometheus-fastapi-instrumentator`)

Response: `intent_label`, `confidence`, `source` (`cache`|`model`|`fallback`), `taxonomy_version`, `model_id` (mirrors configured `LLM_MODEL`).

Empty / trivial input (bare URL-only, etc.) returns `unclassified` with `source="fallback"` without calling the LLM.

## Configuration (env)

| Variable | Purpose |
|-----------|---------|
| `PORT` | HTTP port (default `3010`) |
| `REDIS_URL` | Redis for distributed cache entries |
| `INTENT_TAXONOMY_PATH` | Mounted YAML labels (candidate intents + phrases) |
| `LLM_BASE_URL` | Ollama-compatible chat endpoint, default `http://host.docker.internal:11434/api/chat` |
| `LLM_MODEL` | Model name (`llama3.2`, etc.) |
| `LLM_TIMEOUT_SECONDS` | LLM HTTP timeout |
| `INTENT_CLASSIFIER_CACHE_TTL_SECONDS` / `INTENT_CLASSIFIER_LRU_MAX` | Redis + LRU sizing |

Kubernetes sets these via ConfigMap/secrets aligned with backend `fastapi.yaml` (`INTENT_CLASSIFIER_URL=http://intent-classifier...:3010`).

## Run locally (repo root)

```bash
docker compose up -d intent-classifier redis
# Requires Ollama reachable at LLM_BASE_URL with LLM_MODEL pulled
```

Service listens on `http://localhost:3010`.

## Orchestrator integration

The FastAPI backend calls this service when routing uses **auto-intent**. Configure backend:

- `INTENT_CLASSIFIER_URL` — e.g. `http://intent-classifier.ai-application.svc.cluster.local:3010` (K8s)
- `INTENT_CLASSIFIER_ENABLED` — `true`/`false`
- `INTENT_CLASSIFIER_SHADOW` — log predictions without changing routing
- `INTENT_TAXONOMY_PATH` — same taxonomy file mounted in backend and classifier

## SLO gates

From repository root (Python deps including `httpx`, `torch` only if benchmarks need them):

```bash
pip install httpx pyyaml
python intent_classifier_service/scripts/evaluate_accuracy.py
python intent_classifier_service/scripts/benchmark_latency.py --url http://127.0.0.1:3010
python intent_classifier_service/scripts/run_slo_gate.py --classifier-url http://127.0.0.1:3010
```

**Note:** Latency benchmarks are sensitive to Redis cache warmth and Ollama load. Pass `--vary-text` where supported to stress the LLM path.

## Build image (repo root)

```bash
docker build -f intent_classifier_service/Dockerfile -t api-gateways-intent-classifier:latest .
```
