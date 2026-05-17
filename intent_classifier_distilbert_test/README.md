# Intent classifier — DistilBERT test variant

Parallel test service that mirrors `intent_classifier_service` HTTP behavior (`POST /classify`, `/healthz`, `/readyz`) but uses **HuggingFace zero-shot NLI** (`typeform/distilbert-base-uncased-mnli`) instead of Ollama llama3.

Does **not** modify the production `intent_classifier_service/` folder.

## Quick start (local)

```powershell
cd intent_classifier_distilbert_test
.\scripts\run_local.ps1
```

In another terminal:

```powershell
cd intent_classifier_distilbert_test
.\.venv\Scripts\python.exe scripts\smoke_test.py
```

Default URL: `http://127.0.0.1:3011` (production service uses 3010).

## Local test results (Windows CPU)

| Metric | DistilBERT test (3011) | Production LLM (Ollama) |
|--------|------------------------|-------------------------|
| Cold classify latency | ~120–170 ms | ~5–30 s |
| Cache hit latency | ~2–3 ms | ~1–2 s (Redis) |
| Eval accuracy (`default_test.jsonl`) | ~31% @ threshold 0.30 | Higher when model warm |

DistilBERT is **much faster** but **less accurate** on this taxonomy without tuning. Use `scripts/evaluate_jsonl.py` to compare. Adjust `INTENT_CONFIDENCE_THRESHOLD` and `HYPOTHESIS_TEMPLATE` for your hardware.

## Environment

| Variable | Default | Description |
|----------|---------|-------------|
| `PORT` | `3011` | HTTP port |
| `HF_ZERO_SHOT_MODEL` | `typeform/distilbert-base-uncased-mnli` | Transformers model id |
| `INTENT_TAXONOMY_PATH` | `../intent_taxonomy/intent_labels_v1.yaml` | Shared taxonomy file |
| `REDIS_ENABLED` | `false` | Set `true` + `REDIS_URL` to mirror Redis cache |

## API contract

Same as production:

```json
POST /classify
{"text": "Write a Python function", "tenant_id": "acme-corp"}

→ {"intent_label":"code_generation","confidence":0.82,"source":"model","taxonomy_version":"1","model_id":"typeform/distilbert-base-uncased-mnli"}
```
