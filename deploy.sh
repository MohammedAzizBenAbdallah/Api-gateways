#!/bin/bash

# ─────────────────────────────────────────────────────────────────────────────
# deploy.sh — Enterprise AI Gateway Kubernetes Deployment Script (Bash version)
#
# Usage: ./deploy.sh
# ─────────────────────────────────────────────────────────────────────────────

set -e # Exit immediately if a command exits with a non-zero status.

# Colors
CYAN='\033[0;36m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
GREEN='\033[0;32m'
GRAY='\033[0;90m'
NC='\033[0m' # No Color

echo -e ""
echo -e "${CYAN}==========================================${NC}"
echo -e "${CYAN} Deploying Enterprise AI Gateway to K8s   ${NC}"
echo -e "${CYAN}==========================================${NC}"
echo -e ""

# Functions
ensure_command() {
    local cmd=$1
    if ! command -v "$cmd" &> /dev/null; then
        if [ "$cmd" == "kubectl" ]; then
            echo -e "${YELLOW}Warning: 'kubectl' not found. Attempting to download it locally...${NC}"
            mkdir -p bin
            if curl -LO "https://dl.k8s.io/release/$(curl -L -s https://dl.k8s.io/release/stable.txt)/bin/linux/amd64/kubectl" &> /dev/null; then
                chmod +x kubectl
                mv kubectl bin/
                export PATH="$PATH:$(pwd)/bin"
                echo -e "${GREEN}Local 'kubectl' installed and added to PATH.${NC}"
            else
                echo -e "${RED}Error: Failed to download 'kubectl'. Please install it manually.${NC}"
                exit 1
            fi
        else
            echo -e "${RED}Error: Required command '$cmd' is not available in PATH.${NC}"
            exit 1
        fi
    fi
}

ensure_path() {
    local path_to_check=$1
    if [ ! -e "$path_to_check" ]; then
        echo -e "${RED}Error: Required path is missing: $path_to_check${NC}"
        exit 1
    fi
}

build_local_image() {
    local image_name=$1
    local dockerfile_dir=$2
    local dockerfile_path=$3
    local max_attempts=3

    for ((attempt=1; attempt<=max_attempts; attempt++)); do
        echo -e "${GRAY}  Building image: $image_name (attempt $attempt/$max_attempts)${NC}"
        
        local docker_args=("build" "-t" "$image_name")
        if [ -n "$dockerfile_path" ]; then
            docker_args+=("-f" "$dockerfile_path")
        fi
        docker_args+=("$dockerfile_dir")

        if docker "${docker_args[@]}"; then
            return 0
        else
            local build_exit_code=$?
            if [ $attempt -eq $max_attempts ]; then
                echo -e "${RED}Error: Failed to build image: $image_name${NC}"
                exit 1
            fi
            
            echo -e "${YELLOW}    Retrying build due to potential transient error...${NC}"
            sleep 2
        fi
    done
}

echo -e "${YELLOW}[0/7] Running preflight checks...${NC}"
ensure_command "kubectl"
ensure_command "docker"

# Added local bin to path just in case
export PATH="$PATH:$(pwd)/bin"

if ! kubectl cluster-info &> /dev/null; then
    echo -e "${RED}Error: kubectl cannot reach the active cluster context.${NC}"
    echo -e "${YELLOW}Hint: It seems you don't have a Kubernetes cluster running.${NC}"
    echo -e "You can start a local cluster using 'kind' or 'minikube'."
    echo -e "If you have Docker running, you can install and start 'kind' with:"
    echo -e "  ${CYAN}curl -Lo ./kind https://kind.sigs.k8s.io/dl/v0.20.0/kind-linux-amd64 && chmod +x ./kind && ./kind create cluster${NC}"
    exit 1
fi

ensure_path "k8s/kustomization.yaml"
ensure_path "k8s/secrets/secrets.yaml"
ensure_path "backend/scripts/init-platform-db.sql"
ensure_path "backend/scripts/init-platform-db-usage.sql"
ensure_path "gateway/plugins/simple-validator"
ensure_path "gateway/plugins/tenant-restriction"
ensure_path "gateway/kong_final.yaml"
ensure_path "keycloak/realm-export.json"
ensure_path "monitoring/prometheus.yml"
ensure_path "monitoring/grafana/dashboards"
ensure_path "monitoring/grafana/provisioning/dashboards"
ensure_path "monitoring/grafana/provisioning/datasources"
ensure_path "intent_classifier_service/Dockerfile"

echo -e "${GRAY}  Checking local images required by imagePullPolicy=Never...${NC}"
build_local_image "api-gateways-backend:latest" "fastapi_backend" ""
build_local_image "api-gateways-intent-classifier:latest" "." "intent_classifier_service/Dockerfile"
build_local_image "api-gateways-frontend:latest" "frontend" ""
build_local_image "api-gateways-kong-logger:latest" "kong-logger" ""

metrics_api=$(kubectl api-versions | grep "metrics.k8s.io" || true)
if [ -z "$metrics_api" ]; then
    echo -e "${YELLOW}  Warning: metrics-server API is unavailable; HPAs will report metric errors.${NC}"
fi

# ── Step 1: Create Namespaces ──────────────────────────────────────────────
echo -e ""
echo -e "${YELLOW}[1/7] Creating namespaces...${NC}"
kubectl apply -f k8s/namespaces.yaml

# ── Step 2: Create ConfigMaps for DB init scripts ─────────────────────────
echo -e ""
echo -e "${YELLOW}[2/7] Creating database ConfigMaps...${NC}"
kubectl create configmap platform-db-init-scripts --from-file=init-platform-db.sql=backend/scripts/init-platform-db.sql -n ai-data --dry-run=client -o yaml | kubectl apply -f -
kubectl create configmap platform-db-usage-scripts --from-file=init-platform-db-usage.sql=backend/scripts/init-platform-db-usage.sql -n ai-data --dry-run=client -o yaml | kubectl apply -f -

# ── Step 3: Create Kong plugin & routing ConfigMaps ───────────────────────
echo -e ""
echo -e "${YELLOW}[3/7] Creating Kong plugin & routing ConfigMaps...${NC}"
kubectl create configmap kong-plugin-simple-validator --from-file=gateway/plugins/simple-validator -n ai-gateway --dry-run=client -o yaml | kubectl apply -f -
kubectl create configmap kong-plugin-tenant-restriction --from-file=gateway/plugins/tenant-restriction -n ai-gateway --dry-run=client -o yaml | kubectl apply -f -
kubectl create configmap kong-deck-config --from-file=kong_final.yaml=gateway/kong_final.yaml -n ai-gateway --dry-run=client -o yaml | kubectl apply -f -
kubectl create configmap grafana-dashboards --from-file=monitoring/grafana/dashboards/ -n ai-monitoring --dry-run=client -o yaml | kubectl apply -f -
kubectl create configmap grafana-provisioning-dashboards --from-file=monitoring/grafana/provisioning/dashboards/ -n ai-monitoring --dry-run=client -o yaml | kubectl apply -f -
kubectl create configmap grafana-provisioning-datasources --from-file=monitoring/grafana/provisioning/datasources/ -n ai-monitoring --dry-run=client -o yaml | kubectl apply -f -

# ── Step 4: Create Configuration ConfigMaps ───────────────────────────────
echo -e ""
echo -e "${YELLOW}[4/7] Creating Configuration ConfigMaps...${NC}"
kubectl create configmap keycloak-realm --from-file=realm-export.json=keycloak/realm-export.json -n ai-application --dry-run=client -o yaml | kubectl apply -f -
kubectl create configmap prometheus-config --from-file=prometheus.yml=monitoring/prometheus.yml -n ai-monitoring --dry-run=client -o yaml | kubectl apply -f -

# ── Step 5: Create Kong mTLS certificates (if not exists) ────────────────
echo -e ""
echo -e "${YELLOW}[5/7] Checking Kong mTLS certificates...${NC}"
if ! kubectl get secret kong-cluster-certs -n ai-gateway &> /dev/null; then
    echo -e "${GRAY}  Generating new mTLS certificates...${NC}"
    docker run --rm -v "$(pwd)/k8s/secrets:/certs" alpine/openssl req -new -x509 -nodes -newkey rsa:2048 -keyout /certs/cluster.key -out /certs/cluster.crt -days 1095 -subj "/CN=kong_clustering"
    kubectl create secret tls kong-cluster-certs --cert=k8s/secrets/cluster.crt --key=k8s/secrets/cluster.key -n ai-gateway
else
    echo -e "${GRAY}  Certificates already exist, skipping.${NC}"
fi

# ── Step 6: Deploy everything via Kustomize ───────────────────────────────
echo -e ""
echo -e "${YELLOW}[6/7] Deploying all services...${NC}"
if ! kubectl apply -k k8s/; then
    echo -e "${RED}Error: Step [6/7] failed: kubectl apply -k k8s/ returned non-zero exit code.${NC}"
    exit 1
fi

# ── Wait for services ─────────────────────────────────────────────────────
echo -e ""
echo -e "${GRAY}Waiting for databases...${NC}"
kubectl wait --for=condition=ready pod -l app=platform-db -n ai-data --timeout=180s || (echo -e "${RED}platform-db pods did not become ready in time.${NC}" && exit 1)
kubectl wait --for=condition=ready pod -l app=kong-db -n ai-data --timeout=180s || (echo -e "${RED}kong-db pods did not become ready in time.${NC}" && exit 1)

echo -e "${GRAY}Waiting for application layer...${NC}"
kubectl wait --for=condition=ready pod -l app=fastapi -n ai-application --timeout=900s || (echo -e "${RED}fastapi pods did not become ready in time.${NC}" && exit 1)
kubectl wait --for=condition=ready pod -l app=intent-classifier -n ai-application --timeout=240s || (echo -e "${RED}intent-classifier pods did not become ready in time.${NC}" && exit 1)
kubectl wait --for=condition=ready pod -l app=opa -n ai-application --timeout=120s || (echo -e "${RED}opa pods did not become ready in time.${NC}" && exit 1)

echo -e "${GRAY}Waiting for gateway...${NC}"
if ! kubectl wait --for=condition=ready pod -l app=kong-cp -n ai-gateway --timeout=240s; then
    echo -e "${YELLOW}  Kong CP did not become ready; restarting control plane once...${NC}"
    kubectl rollout restart deployment/kong-cp -n ai-gateway
    kubectl rollout status deployment/kong-cp -n ai-gateway --timeout=240s || (echo -e "${RED}kong-cp failed to become ready after restart.${NC}" && exit 1)
fi

# ── Step 7: Sync Kong Configuration using Deck ────────────────────────────
echo -e ""
echo -e "${YELLOW}[7/7] Synchronizing Kong Configuration...${NC}"
if ! kubectl apply -f k8s/gateway/kong-deck-sync.yaml; then
    echo -e "${RED}Error: Failed to create kong-deck-sync job.${NC}"
    exit 1
fi

if ! kubectl wait --for=condition=complete job/kong-deck-sync -n ai-gateway --timeout=180s; then
    echo -e "${RED}  kong-deck-sync failed; dumping job logs...${NC}"
    kubectl logs job/kong-deck-sync -n ai-gateway --tail=200
    echo -e "${RED}Error: kong-deck-sync job did not complete successfully.${NC}"
    exit 1
fi

# ── Final Status ──────────────────────────────────────────────────────────
echo -e ""
echo -e "${GREEN}==========================================${NC}"
echo -e "${GREEN} Deployment Complete!                     ${NC}"
echo -e "${GREEN}==========================================${NC}"
echo -e ""
echo -e "Pod Status:"
kubectl get pods -A
echo -e ""
echo -e "${CYAN}Next step: run ./start-ui.sh to access the UI${NC}"
echo -e ""
