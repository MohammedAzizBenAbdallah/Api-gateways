# Chat API test results

**Date:** 2026-05-16  
**Endpoint:** `POST http://localhost/api/ai/request` (via Kong)  
**Tenant:** `acme-corp`  
**Tooling:** [scripts/measure_first_token.py](scripts/measure_first_token.py), [scripts/run_chat_test_matrix.py](scripts/run_chat_test_matrix.py)

## Prerequisites

| Check | Result |
|-------|--------|
| Ollama `http://localhost:11434/api/tags` | 200 |
| Kong `http://localhost` | 200 |
| FastAPI / intent-classifier pods | Running |
| JWT | Initial plan token; refreshed via Keycloak `test`/`test` for tests B–D retry |

**Note:** `platform-db` restarted mid-run (connection refused → 500s on tests 4–D). Retries after DB recovery succeeded.

---

## Results checklist

| Test | HTTP | Non-empty tokens | Service / intent (logs) | First token &lt; 3s |
|------|------|------------------|-------------------------|---------------------|
| 1 `general_chat` | 200 | Yes (`Hello!`) | `general_chat` → `ollama-llama3` | **No** (30,850 ms) |
| 2 `code_generation` | 200 | Yes (494 chunks) | `code_generation` → `ollama-DeepSeekCoder` | **No** (18,638 ms) |
| 3 `summarization` | 200 | Yes (retry) | `summarization` → `ollama-llama3` | **No** (15,592 ms) |
| 4 `advanced_chat` | 200 | Yes (retry) | `advanced_chat` → `gemini-cloud` | **No** (15,978 ms) |
| A auto → general | 200 | Yes | `predicted_intent=general_chat` → `ollama-llama3` | **No** (24,373 ms) |
| B auto → code | 200 | Yes | **`predicted_intent=general_chat`** → `ollama-llama3` (expected code) | **No** (9,192 ms) |
| C auto → summary | 200 | Yes | `predicted_intent=summarization` → `ollama-llama3` | **No** (55,420 ms) |
| D auto → advanced | 200 | Yes | `predicted_intent=advanced_chat` → `gemini-cloud` | **No** (46,774 ms) |

**Summary:** 8/8 returned HTTP 200 with non-empty streamed tokens (after retries). 7/8 auto/manual routing correct; **test B mis-routed** (classifier cache returned `general_chat` for the React bug prompt).

---

## NFR: first-token latency &lt; 3 seconds

| Metric | Result |
|--------|--------|
| All runs under 3s | **0/8** |
| Fastest first token | ~9.2s (auto B, wrong intent) |
| Slowest first token | ~61s (auto A, first matrix run) |

First-token time includes full pre-flight (intent, OPA, PII, DB) plus Ollama/Gemini cold start. **NFR not met** in this environment.

---

## Routing verification (log excerpts)

```
# Manual
provided_intent=general_chat resolved_intent=general_chat resolved_service=ollama-llama3 mode=manual
provided_intent=code_generation resolved_intent=code_generation resolved_service=ollama-DeepSeekCoder mode=manual

# Auto
predicted_intent=general_chat ... resolved_service=ollama-llama3 mode=auto
predicted_intent=summarization confidence=1.0 source=model ... resolved_service=ollama-llama3 mode=auto
predicted_intent=advanced_chat confidence=0.95 source=model ... resolved_service=gemini-cloud mode=auto
```

---

## Issues observed

1. **Platform DB restart** during long matrix run → transient 500 / `Connection refused` / `IncompleteRead`.
2. **JWT expiry** during multi-minute run → 401 on tests C/D until token refreshed.
3. **Classifier cache** (`source=cache`) caused test B to reuse `general_chat` instead of `code_generation`.
4. **First-token NFR** dominated by pre-flight + local Ollama load times (15–61s), not gateway/auth.

---

## After fixes (2026-05-16)

Postgres probes/memory tuned (`k8s/data/databases.yaml`, `postgres-platform.yaml`). FastAPI: early SSE `{"status":"thinking"}`, parallel pre-flight phase A, SSE error frames. Frontend: shared HTTP/SSE error handling. `measure_first_token.py` uses 1-byte reads and tracks `first_event_ms` vs model TTFT.

| Test | HTTP | First SSE event &lt; 3s | Model TTFT &lt; 3s | Routing |
|------|------|-------------------------|---------------------|---------|
| 1 `general_chat` | 200 | **Yes** (255 ms) | No (4.6s) | OK |
| 2 `code_generation` | 200 | **Yes** (217 ms) | No (8.5s) | OK |
| 3 `summarization` | 200 | **Yes** (636 ms) | No (31.8s) | OK |
| 4 `advanced_chat` | 200 | **Yes** (325 ms) | No (37.3s) | OK |
| A auto → general | 200 | **Yes** (1.2s) | No (33.2s) | OK |
| B auto → code | 200 | **Yes** (467 ms) | No (18.8s) | **Mis-routed** (`general_chat` cache) |
| C auto → summary | 200 | **Yes** (365 ms) | No (13.2s) | OK |
| D auto → advanced | 200 | **Yes** (395 ms) | No (16.0s) | OK |

**Summary:** 8/8 HTTP 200; **8/8 first SSE event &lt; 3s** (product NFR); **0/8 model TTFT &lt; 3s** (Ollama/Gemini load still dominates). 7/8 routing correct; test B still hits classifier cache with wrong label (`source=cache`, `predicted_intent=general_chat`). No DB CrashLoop during matrix after probe fix.

---

## How to re-run

```powershell
$body = @{ client_id='myclient'; grant_type='password'; username='test'; password='test' }
$env:BEARER_TOKEN = (Invoke-RestMethod -Uri 'http://localhost/auth/realms/newRealm/protocol/openid-connect/token' -Method POST -Body $body -ContentType 'application/x-www-form-urlencoded').access_token
$env:CHAT_URL = 'http://localhost/api/ai/request'
python scripts/run_chat_test_matrix.py
```

Raw JSON: [chat-test-results.json](chat-test-results.json) (partial first run; see table above for merged outcomes).
