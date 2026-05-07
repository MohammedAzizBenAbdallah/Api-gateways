# Intent classifier microservice

FastAPI service that assigns **exactly one** intent label per request. It runs **keyword heuristics first** (summary TL;DR cues, programming cues, greetings, etc.), then HuggingFace **zero-shot** NLI (`typeform/distilbert-base-uncased-mnli`) with short **label hypotheses** and a neutral template (`This is related to {}.` — avoid putting the word “text” in the template; it biases toward summarization). Results are cached in **Redis** (DB index `1` recommended) plus an in-process LRU.

## API

- `POST /classify` — body `{"text": "...", "tenant_id": "optional", "environment": "optional"}`
- `GET /healthz` — process up
- `GET /readyz` — model loaded
- `GET /metrics` — Prometheus (instrumentator)

Response: `intent_label`, `confidence`, `source` (`cache`|`model`|`fallback`), `taxonomy_version`, `model_id`.

Low-confidence or invalid model output maps to `unclassified` (not an NLI candidate; enforced via threshold).

## Run locally (repo root)

```bash
docker compose up -d intent-classifier redis
# first boot downloads the HF model (may take minutes)
```

Service listens on `http://localhost:3010`.

## Orchestrator integration

The FastAPI backend calls this service when `intent` is set to `auto` (`INTENT_AUTO_TOKEN`, default `auto`). Configure:

- `INTENT_CLASSIFIER_URL` — e.g. `http://intent-classifier:3010`
- `INTENT_CLASSIFIER_ENABLED` — `true`/`false`
- `INTENT_CLASSIFIER_SHADOW` — log predicted vs provided intent without changing routing
- `INTENT_TAXONOMY_PATH` — path to shared `intent_labels_v1.yaml`

## SLO gates

From repository root (requires Python deps: `transformers`, `torch`, `httpx`, `pyyaml`):

```bash
pip install transformers torch httpx pyyaml
python intent_classifier_service/scripts/evaluate_accuracy.py
python intent_classifier_service/scripts/benchmark_latency.py --url http://127.0.0.1:3010
python intent_classifier_service/scripts/run_slo_gate.py --classifier-url http://127.0.0.1:3010
```

**Note:** P95 \< 100 ms targets the **warm cache** path. By default `benchmark_latency.py` repeats the same text (high cache hit rate). Pass `--vary-text` to stress the model path (typically much slower on CPU).

## Build image (repo root)

```bash
docker build -f intent_classifier_service/Dockerfile -t api-gateways-intent-classifier:latest .
```
