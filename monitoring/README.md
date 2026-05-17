# Monitoring Pipeline (YAML-First)

This project is configured so the full monitoring stack boots from:

```bash
docker compose up -d --build
```

No manual Grafana setup is required. Everything is Git-tracked and provisioned from YAML/JSON in this folder.

## Host Ollama (chat latency)

Pods reach the host Ollama API via `host.docker.internal:11434`. On Windows, **`deploy.ps1`** (run as Administrator on first setup) sets machine-level **`OLLAMA_KEEP_ALIVE=-1`** so models stay loaded after the first request. Verify with `ollama ps` after a chat message.

## What starts automatically

- `prometheus` (`:9090`) - scrapes metrics, evaluates Prometheus alert rules
- `alertmanager` (`:9093`) - routes alerts (no-op `default-log` receiver until you wire up a webhook)
- `grafana` (`:3001`) - dashboards + Grafana-managed alerts (anonymous Viewer enabled)
- `loki` (`:3100`) - log aggregation backend, single-binary mode with local FS storage
- `promtail` - tails `kong-logger/logs/access-*.jsonl` and pushes to Loki
- `kong-logger` (`:8888`) - receives the Kong `http-log` plugin payloads, writes JSONL files and inserts AWS-shaped rows into `platform-db.api_usage_records`

## Source-of-truth files

- Prometheus scrape + alerting config: [`monitoring/prometheus.yml`](prometheus.yml)
- Prometheus alert rules: [`monitoring/prometheus/rules/*.yml`](prometheus/rules/)
- Alertmanager routing config: [`monitoring/alertmanager/alertmanager.yml`](alertmanager/alertmanager.yml)
- Grafana datasource provisioning: [`monitoring/grafana/provisioning/datasources/datasource.yml`](grafana/provisioning/datasources/datasource.yml)
- Grafana dashboard provisioning: [`monitoring/grafana/provisioning/dashboards/dashboards.yml`](grafana/provisioning/dashboards/dashboards.yml)
- Grafana-managed alerts: [`monitoring/grafana/provisioning/alerting/*.yml`](grafana/provisioning/alerting/)
- Grafana dashboard definitions: [`monitoring/grafana/dashboards/*.json`](grafana/dashboards/)
- Loki config: [`monitoring/loki/local-config.yaml`](loki/local-config.yaml)
- Promtail config: [`monitoring/promtail/promtail-config.yaml`](promtail/promtail-config.yaml)
- Kong declarative plugin config: [`gateway/kong_final.yaml`](../gateway/kong_final.yaml)

## End-to-end data flow

```
[kong-dp] --(/metrics 8100)----------------------> [prometheus] --rules--> [alertmanager]
[kong-dp] --(http-log plugin)---> [kong-logger] --insert--> [platform-db.api_usage_records]
                                  [kong-logger] --append--> [kong-logger/logs/access-*.jsonl]
                                                            [promtail] --tail--> [loki]

[grafana] reads: prometheus + platform-db (postgres) + loki + alertmanager
```

1. FastAPI exposes metrics at `backend:3000/metrics`.
2. Kong (data plane) exposes metrics at `kong-dp:8100/metrics` via the Status API and the declarative `prometheus` plugin. The control plane (`kong-cp`) is private and not scraped.
3. Prometheus scrapes both targets and evaluates alert rules. Active alerts go to Alertmanager.
4. The global `http-log` plugin on `kong-dp` POSTs every request to `kong-logger:8888`, which writes a JSONL line and inserts an AWS-shaped row into `platform_permissions.api_usage_records`.
5. Promtail tails the JSONL files and pushes them to Loki, parsing the JSON so `apiId`, `stage`, and `status` are searchable as labels.
6. Grafana reads Prometheus, the `PlatformDB` Postgres datasource, Loki, and Alertmanager. The Admin Portal frontend embeds dashboards by UID (`iframe` URLs under `http://localhost:3001/`).

### Kubernetes (`k8s/` manifests)

Cluster Grafana listens on **container port 3000**, with `GF_SERVER_ROOT_URL` pointing at **`http://localhost:3000/grafana/`** when exposed via port-forward.

The SPA’s **Admin Portal → Observability** iframes still use **`http://localhost:3001/...`** so they match Docker Compose. Forward the in-cluster Service to local **3001** (not 3000):

```bash
kubectl port-forward -n ai-monitoring svc/grafana 3001:3000
```

`start-ui.ps1` opens that forward. If you open Grafana at `localhost:3000` only, Compose-style embed URLs in the Admin Portal will stay blank until you add a second forward on 3001 or change the iframe URLs.

## Where do I look for X?

| Question | Source | How |
| --- | --- | --- |
| Kong/FastAPI service health, request rates, latencies (Prometheus metrics) | Prometheus / Grafana | `kong_official` or `fastapi_app` dashboards (Grafana 3001) |
| Per-route, per-API, per-consumer access patterns | Postgres (`api_usage_records`) | `API Gateway Overview`, `API Gateway - Per API`, `API Gateway - Per Consumer` dashboards |
| Errors with full request context (status, error_type, source IP) | Postgres + Loki | `API Gateway - Errors` dashboard (Postgres table + Loki Logs panel) |
| Billing aggregates (requests/bytes per API per hour) | Postgres view `api_usage_hourly` | Direct SQL or per-consumer dashboard |
| Raw access log lines (CloudWatch-Logs-Insights-style) | Loki via Grafana Explore | `{job="kong-access"} \| json \| ...` |
| Active alerts (Prometheus or Grafana-managed) | Alertmanager / Grafana Alerting | `:9093` or Grafana -> Alerting -> Alert rules |
| Is kong-logger ingesting? | Grafana alert + `kong-logger/health` | `KongLoggerIngestionStalled` alert + `curl localhost:8888/health` |

## Dashboards (provisioned)

- `kong_official` - Prometheus-backed Kong dashboard.
- `fastapi_app` - Prometheus-backed FastAPI dashboard.
- `nextora_bi` - product-side BI panels.
- `api_gateway_overview` - global request rate, latency p50/p95/p99, status mix, top routes, billing counters. **Postgres-backed.**
- `api_gateway_per_api` - drill-down by `api_id` (template var). Latency heatmap, top consumers, recent 50 requests. **Postgres-backed.**
- `api_gateway_per_consumer` - drill-down by `consumer_username` (template var). Bytes processed, APIs touched, 4xx/5xx counts. **Postgres-backed.**
- `api_gateway_errors` - 4xx/5xx rate, integration errors, recent error table, **plus a Loki logs panel** for the same time window.

## Alerts

### Prometheus (in [`prometheus/rules/api-gateway-alerts.yml`](prometheus/rules/api-gateway-alerts.yml))

- `FastApiTargetDown` - backend `/metrics` not scrapable for 2m
- `KongTargetDown` - `kong-dp:8100/metrics` not scrapable for 2m
- `ElevatedFastApi5xxRate` - FastAPI 5xx > 0.2 req/s for 5m
- `Kong5xxRateHigh` - Kong 5xx share > 1% over 5m (from `kong_http_requests_total`)
- `KongP95LatencyHigh` - p95 of `kong_request_latency_ms` > 1s over 5m
- `KongClusterDataPlaneStale` - prometheus plugin metrics missing or DP target down for 2m

### Grafana-managed (in [`grafana/provisioning/alerting/log-ingestion.yml`](grafana/provisioning/alerting/log-ingestion.yml))

- `KongLoggerIngestionStalled` - Postgres-backed. Fires when `max(request_time)` in `api_usage_records` is more than 120s behind wall-clock for 5m. Equivalent of CloudWatch's "ApiGateway logs delivery latency".

### Alert delivery

`alertmanager.yml` ships with only a no-op `default-log` receiver to avoid spamming destinations you haven't configured. A commented webhook receiver scaffold lives in the same file - flipping `route.receiver: default-log` to `route.receiver: webhook` (one-line edit) is all it takes once you have somewhere to send alerts.

## SQL recipes (PlatformDB - `platform_permissions`)

Use Grafana Explore with the `PlatformDB` datasource, or `psql` directly.

**Requests per consumer in the last hour:**

```sql
SELECT COALESCE(consumer_username, consumer_id, '<anon>') AS consumer,
       COUNT(*) AS requests,
       SUM(data_processed_bytes) AS bytes,
       AVG(response_latency_ms)::numeric(10,1) AS avg_ms
FROM api_usage_records
WHERE request_time > now() - interval '1 hour'
GROUP BY 1
ORDER BY requests DESC;
```

**Top 4xx paths today:**

```sql
SELECT api_id, http_method, path, COUNT(*) AS hits
FROM api_usage_records
WHERE status BETWEEN 400 AND 499
  AND request_time > date_trunc('day', now())
GROUP BY 1, 2, 3
ORDER BY hits DESC
LIMIT 25;
```

**Per-API hourly billing rollup (uses provisioned view):**

```sql
SELECT bucket_hour, api_id, request_count, data_processed_bytes, error_count, avg_latency_ms
FROM api_usage_hourly
WHERE bucket_hour > now() - interval '24 hours'
ORDER BY bucket_hour DESC, api_id;
```

**Billing reconciliation between JSONL and Postgres** (verifies the file sink and the Postgres sink agree on what they ingested - useful when the `kong-logger` queue stats showed drops):

```bash
# JSONL count for the rotation file of the day
wc -l kong-logger/logs/access-$(date +%Y-%m-%d).jsonl

# Postgres count for the same UTC day
docker compose exec platform-db psql -U platform_admin -d platform_permissions -c \
  "SELECT COUNT(*) FROM api_usage_records WHERE request_time::date = current_date;"
```

If the two diverge by more than the queue drop count reported by `curl localhost:8888/health`, something else is wrong (Postgres lag, schema mismatch, transform bug).

## LogQL examples (Loki, via Grafana Explore)

The Promtail pipeline parses JSONL fields and promotes `api_id`, `stage`, and `status` to labels. Everything else stays in the line and is reachable via `| json`.

**All logs from a tenant:**

```logql
{job="kong-access"} | json | identity_caller="acme-tenant"
```

**Slow requests on one API (>500ms):**

```logql
{job="kong-access", api_id="fastapi"} | json | response_latency > 500
```

**A specific request id (correlate with `X-Request-ID` header / Postgres `request_id`):**

```logql
{job="kong-access"} |= "abc-123-uuid"
```

**4xx errors only, last 15m, with the `error.responseType` field surfaced:**

```logql
{job="kong-access", status=~"4.."} | json | line_format "{{.requestTime}} {{.apiId}} {{.path}} -> {{.status}} ({{.error_responseType}})"
```

## Quick validation after startup

1. Prometheus targets: <http://localhost:9090/targets> - all `UP`.
2. Alertmanager: <http://localhost:9093>.
3. Grafana: <http://localhost:3001>. Datasources: `Prometheus`, `PlatformDB`, `Alertmanager`, `Loki`.
4. Admin Portal observability tab — panels populate when Grafana is reachable at **localhost:3001** (Compose, or K8s forward `3001:3000` — see **Kubernetes** note above).
5. Throw a small load burst:
   ```bash
   docker run --rm --network apigatewaydemo_default williamyeh/wrk -t2 -c20 -d10s http://kong-dp:8000/api/healthz
   ```
   - `API Gateway Overview` request rate rises.
   - `API Gateway - Errors` table populates and the Loki panel shows matching JSONL lines.
6. Force the Grafana ingestion-stall alert: `docker compose pause kong-logger`. After ~5m the `KongLoggerIngestionStalled` alert fires (Grafana Alerting -> Alertmanager). `docker compose unpause kong-logger` to resolve.
