# Monitoring Pipeline (YAML-First)

This project is configured so the full monitoring stack boots from:

```bash
docker compose up -d --build
```

No manual Grafana setup is required. Everything is Git-tracked and provisioned from YAML/JSON in this folder.

## What starts automatically

- `prometheus` (`:9090`) for scraping metrics and evaluating rules
- `alertmanager` (`:9093`) for alert routing
- `grafana` (`:3001`) for dashboards embedded in the Admin Portal

## Source-of-truth files

- Prometheus scrape + alerting config: `monitoring/prometheus.yml`
- Prometheus alert rules: `monitoring/prometheus/rules/*.yml`
- Alertmanager routing config: `monitoring/alertmanager/alertmanager.yml`
- Grafana datasource provisioning: `monitoring/grafana/provisioning/datasources/datasource.yml`
- Grafana dashboard provisioning: `monitoring/grafana/provisioning/dashboards/dashboards.yml`
- Grafana dashboard definitions: `monitoring/grafana/dashboards/*.json`
- Kong declarative plugin config: `gateway/kong_final.yaml`

## End-to-end data flow

1. FastAPI exposes metrics at `backend:3000/metrics`.
2. Kong exposes metrics at `kong:8001/metrics` (via declarative `prometheus` plugin).
3. Prometheus scrapes both targets and evaluates alert rules.
4. Prometheus sends active alerts to Alertmanager.
5. Grafana reads Prometheus and Alertmanager datasources.
6. Frontend Admin Portal embeds Grafana dashboards by UID in iframe tabs.

## Quick validation after startup

1. Open Prometheus targets: `http://localhost:9090/targets` and ensure jobs are `UP`.
2. Open Alertmanager: `http://localhost:9093`.
3. Open Grafana: `http://localhost:3001` (anonymous viewer enabled in compose).
4. Open Admin Portal observability tab and verify panels are populated.
