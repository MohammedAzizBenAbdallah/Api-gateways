# ─────────────────────────────────────────────────────────────────────────────
# Makefile  —  Enterprise AI Gateway Kubernetes Shortcuts
#
# Usage:
#   make deploy      → Deploy the entire platform
#   make status      → Show all pods across all namespaces
#   make teardown    → Remove everything
#   make logs        → Tail FastAPI logs
#   make admin       → Open Kong Admin API via port-forward
# ─────────────────────────────────────────────────────────────────────────────

.PHONY: help deploy preflight build-local-images status teardown logs logs-kong logs-opa admin grafana restart-fastapi restart-kong

KUBECTL = kubectl
NAMESPACES = ai-data ai-application ai-gateway ai-monitoring

# ── Default target ────────────────────────────────────────────────────────────
help:
	@echo ""
	@echo "  Enterprise AI Gateway — Kubernetes Makefile"
	@echo "  ──────────────────────────────────────────────────────────"
	@echo "  make deploy          Deploy the entire platform to Kubernetes"
	@echo "  make preflight       Validate tools, files, and cluster connectivity"
	@echo "  make build-local-images Build local images used by Kubernetes manifests"
	@echo "  make status          Show all pods and their health across all namespaces"
	@echo "  make teardown        Remove ALL resources (warning: deletes PVCs/data)"
	@echo "  make logs            Stream FastAPI backend logs"
	@echo "  make logs-kong       Stream Kong Data Plane logs"
	@echo "  make logs-opa        Stream OPA policy engine logs"
	@echo "  make admin           Port-forward Kong Admin API to localhost:8001"
	@echo "  make grafana         Port-forward Grafana to localhost:3001"
	@echo "  make restart-fastapi Rolling restart of FastAPI pods"
	@echo "  make restart-kong    Rolling restart of Kong Data Plane pods"
	@echo "  make hpa             Show autoscaler status"
	@echo ""

# ── Deploy ────────────────────────────────────────────────────────────────────
deploy: preflight build-local-images
	@echo "🚀 Deploying Enterprise AI Gateway to Kubernetes..."
	@echo "📦 Creating ConfigMaps for database initialization and Kong plugins..."
	$(KUBECTL) apply -f k8s/namespaces.yaml
	$(KUBECTL) create configmap platform-db-init-scripts --from-file=init-platform-db.sql=backend/scripts/init-platform-db.sql -n ai-data --dry-run=client -o yaml | $(KUBECTL) apply -f -
	$(KUBECTL) create configmap platform-db-usage-scripts --from-file=init-platform-db-usage.sql=backend/scripts/init-platform-db-usage.sql -n ai-data --dry-run=client -o yaml | $(KUBECTL) apply -f -
	$(KUBECTL) create configmap kong-plugin-simple-validator --from-file=gateway/plugins/simple-validator -n ai-gateway --dry-run=client -o yaml | $(KUBECTL) apply -f -
	$(KUBECTL) create configmap kong-plugin-tenant-restriction --from-file=gateway/plugins/tenant-restriction -n ai-gateway --dry-run=client -o yaml | $(KUBECTL) apply -f -
	$(KUBECTL) create configmap kong-deck-config --from-file=kong_final.yaml=gateway/kong_final.yaml -n ai-gateway --dry-run=client -o yaml | $(KUBECTL) apply -f -
	@echo "🔑 Generating Configuration ConfigMaps..."
	$(KUBECTL) create configmap keycloak-realm --from-file=realm-export.json=keycloak/realm-export.json -n ai-application --dry-run=client -o yaml | $(KUBECTL) apply -f -
	$(KUBECTL) create configmap prometheus-config --from-file=prometheus.yml=monitoring/prometheus.yml -n ai-monitoring --dry-run=client -o yaml | $(KUBECTL) apply -f -
	$(KUBECTL) apply -k k8s/
	@echo ""
	@echo "⏳ Waiting for databases to be ready..."
	$(KUBECTL) wait --for=condition=ready pod -l app=platform-db -n ai-data --timeout=120s
	$(KUBECTL) wait --for=condition=ready pod -l app=kong-db -n ai-data --timeout=120s
	@echo ""
	@echo "⏳ Waiting for application layer to be ready..."
	$(KUBECTL) wait --for=condition=ready pod -l app=fastapi -n ai-application --timeout=180s
	$(KUBECTL) wait --for=condition=ready pod -l app=opa -n ai-application --timeout=60s
	@echo ""
	@echo "⏳ Waiting for gateway..."
	$(KUBECTL) wait --for=condition=ready pod -l app=kong-cp -n ai-gateway --timeout=120s 2>/dev/null || true
	@echo "🔄 Synchronizing Kong Configuration..."
	$(KUBECTL) apply -f k8s/gateway/kong-deck-sync.yaml
	$(KUBECTL) wait --for=condition=complete job/kong-deck-sync -n ai-gateway --timeout=60s 2>/dev/null || true
	@echo ""
	$(KUBECTL) wait --for=condition=ready pod -l app=kong-dp -n ai-gateway --timeout=120s
	@echo ""
	@echo "✅ Deployment complete!"
	@make status

# ── Preflight ─────────────────────────────────────────────────────────────────
preflight:
	@echo "🔎 Running Kubernetes preflight checks..."
	@kubectl cluster-info >/dev/null || (echo "Cluster unreachable (kubectl cluster-info failed)"; exit 1)
	@test -f k8s/kustomization.yaml
	@test -f k8s/secrets/secrets.yaml
	@test -f backend/scripts/init-platform-db.sql
	@test -f backend/scripts/init-platform-db-usage.sql
	@test -d gateway/plugins/simple-validator
	@test -d gateway/plugins/tenant-restriction
	@test -f gateway/kong_final.yaml
	@test -f keycloak/realm-export.json
	@test -f monitoring/prometheus.yml
	@test -d monitoring/grafana/dashboards
	@test -d monitoring/grafana/provisioning/dashboards
	@test -d monitoring/grafana/provisioning/datasources
	@echo "✅ Preflight checks passed."
	@kubectl api-versions | grep -q metrics.k8s.io || echo "⚠️  metrics-server API not available; HPA metrics warnings are expected."

# ── Local image build ─────────────────────────────────────────────────────────
build-local-images:
	@echo "🐳 Building local Kubernetes images..."
	@docker build -t api-gateways-backend:latest fastapi_backend
	@docker build -t api-gateways-frontend:latest frontend
	@docker build -t api-gateways-kong-logger:latest kong-logger
	@echo "✅ Local images ready."

# ── Status ────────────────────────────────────────────────────────────────────
status:
	@echo ""
	@echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
	@echo " Enterprise AI Gateway — System Status"
	@echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
	@echo ""
	@echo "📦 LAYER 4 — DATA"
	@$(KUBECTL) get pods -n ai-data -o wide
	@echo ""
	@echo "⚙️  LAYER 3 — APPLICATION"
	@$(KUBECTL) get pods -n ai-application -o wide
	@echo ""
	@echo "🔀 LAYER 2 — GATEWAY"
	@$(KUBECTL) get pods -n ai-gateway -o wide
	@echo ""
	@echo "📊 MONITORING"
	@$(KUBECTL) get pods -n ai-monitoring -o wide
	@echo ""
	@echo "🌐 SERVICES (External IPs)"
	@$(KUBECTL) get services -n ai-gateway --field-selector spec.type=LoadBalancer
	@echo ""

# ── Teardown ──────────────────────────────────────────────────────────────────
teardown:
	@echo "⚠️  WARNING: This will delete ALL resources including persistent data!"
	@read -p "Are you sure? (yes/no): " confirm && [ "$$confirm" = "yes" ] || exit 1
	$(KUBECTL) delete -k k8s/ --ignore-not-found=true
	@echo "✅ All resources removed."

# ── Logs ──────────────────────────────────────────────────────────────────────
logs:
	$(KUBECTL) logs -n ai-application -l app=fastapi --tail=100 -f

logs-kong:
	$(KUBECTL) logs -n ai-gateway -l app=kong-dp --tail=100 -f

logs-opa:
	$(KUBECTL) logs -n ai-application -l app=opa --tail=100 -f

logs-keycloak:
	$(KUBECTL) logs -n ai-application -l app=keycloak --tail=100 -f

# ── Port Forwarding ───────────────────────────────────────────────────────────
admin:
	@echo "🔑 Kong Admin API → http://localhost:8001"
	@echo "   Press Ctrl+C to stop"
	$(KUBECTL) port-forward -n ai-gateway svc/kong-cp 8001:8001

grafana:
	@echo "📊 Grafana → http://localhost:3001"
	@echo "   Login: admin / admin"
	@echo "   Press Ctrl+C to stop"
	$(KUBECTL) port-forward -n ai-monitoring svc/grafana 3001:3000

prometheus:
	@echo "📈 Prometheus → http://localhost:9090"
	$(KUBECTL) port-forward -n ai-monitoring svc/prometheus 9090:9090

# ── Rolling Restarts ──────────────────────────────────────────────────────────
restart-fastapi:
	@echo "🔄 Rolling restart of FastAPI (zero downtime)..."
	$(KUBECTL) rollout restart deployment/fastapi -n ai-application
	$(KUBECTL) rollout status deployment/fastapi -n ai-application

restart-kong:
	@echo "🔄 Rolling restart of Kong Data Plane (zero downtime)..."
	$(KUBECTL) rollout restart deployment/kong-dp -n ai-gateway
	$(KUBECTL) rollout status deployment/kong-dp -n ai-gateway

# ── Autoscaling Status ────────────────────────────────────────────────────────
hpa:
	@echo ""
	@echo "⚡ Autoscaler Status"
	@echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
	$(KUBECTL) get hpa -n ai-application
	$(KUBECTL) get hpa -n ai-gateway
