# ─────────────────────────────────────────────────────────────────────────────
# deploy.ps1  —  Enterprise AI Gateway Kubernetes Deployment Script
#
# Usage:  .\deploy.ps1
#
# Images are built as local :latest tags (imagePullPolicy Never in manifests).
# That matches single-node dev clusters (Docker Desktop, Minikube). For
# multi-node production, push images to your registry, point manifests at those
# references, and use imagePullPolicy: IfNotPresent or Always as appropriate.
# ─────────────────────────────────────────────────────────────────────────────

Write-Host ""
Write-Host "==========================================" -ForegroundColor Cyan
Write-Host " Deploying Enterprise AI Gateway to K8s"   -ForegroundColor Cyan
Write-Host "==========================================" -ForegroundColor Cyan
Write-Host ""

function Ensure-Command {
    param(
        [string]$Name
    )
    if (-not (Get-Command $Name -ErrorAction SilentlyContinue)) {
        throw "Required command '$Name' is not available in PATH."
    }
}

function Ensure-Path {
    param(
        [string]$PathToCheck
    )
    if (-not (Test-Path $PathToCheck)) {
        throw "Required path is missing: $PathToCheck"
    }
}

function Build-LocalImage {
    param(
        [string]$ImageName,
        [string]$DockerfileDir,
        [string]$DockerfilePath = ""
    )
    $maxAttempts = 3
    for ($attempt = 1; $attempt -le $maxAttempts; $attempt++) {
        Write-Host "  Building image: $ImageName (attempt $attempt/$maxAttempts)" -ForegroundColor Gray
        $dockerArgs = @("build", "-t", $ImageName)
        if ($DockerfilePath) {
            $dockerArgs += @("-f", $DockerfilePath)
        }
        $dockerArgs += $DockerfileDir
        $buildOutput = & docker @dockerArgs 2>&1
        $buildText = ($buildOutput | Out-String)
        if ($buildText) {
            Write-Host $buildText
        }
        $exitCode = $LASTEXITCODE

        if ($exitCode -eq 0) {
            return
        }

        $isTlsHandshakeTimeout = $buildText -match "TLS handshake timeout"
        $isRegistryMetadataFailure = $buildText -match "failed to resolve source metadata"

        $isRetryable = $isTlsHandshakeTimeout -or $isRegistryMetadataFailure
        if (-not $isRetryable -or $attempt -eq $maxAttempts) {
            throw "Failed to build image: $ImageName"
        }

        Write-Host "    Retrying build due to transient registry/network error..." -ForegroundColor Yellow
    }
}

Write-Host "[0/7] Running preflight checks..." -ForegroundColor Yellow
Ensure-Command "kubectl"
Ensure-Command "docker"
kubectl cluster-info | Out-Null
if ($LASTEXITCODE -ne 0) {
    throw "kubectl cannot reach the active cluster context."
}
Ensure-Path "k8s\kustomization.yaml"
Ensure-Path "k8s\secrets\secrets.yaml"
Ensure-Path "backend\scripts\init-platform-db.sql"
Ensure-Path "backend\scripts\init-platform-db-usage.sql"
Ensure-Path "gateway\plugins\simple-validator"
Ensure-Path "gateway\plugins\tenant-restriction"
Ensure-Path "gateway\kong_final.yaml"
Ensure-Path "keycloak\realm-export.json"
Ensure-Path "monitoring\prometheus.yml"
Ensure-Path "monitoring\grafana\dashboards"
Ensure-Path "monitoring\grafana\provisioning\dashboards"
Ensure-Path "monitoring\grafana\provisioning\datasources"
Ensure-Path "intent_classifier_service\Dockerfile"

Write-Host "  Checking local images required by imagePullPolicy=Never..." -ForegroundColor Gray
Build-LocalImage "api-gateways-backend:latest" "fastapi_backend"
Build-LocalImage "api-gateways-intent-classifier:latest" "." "intent_classifier_service/Dockerfile"
Build-LocalImage "api-gateways-frontend:latest" "frontend"
Build-LocalImage "api-gateways-kong-logger:latest" "kong-logger"

$metricsApi = kubectl api-versions | Select-String "metrics.k8s.io"
if (-not $metricsApi) {
    Write-Host "  Warning: metrics-server API is unavailable; HPAs will report metric errors." -ForegroundColor Yellow
}

# ── Step 1: Create Namespaces ──────────────────────────────────────────────
Write-Host ""
Write-Host "[1/7] Creating namespaces..." -ForegroundColor Yellow
kubectl apply -f k8s/namespaces.yaml

# ── Step 2: Create ConfigMaps for DB init scripts ─────────────────────────
Write-Host ""
Write-Host "[2/7] Creating database ConfigMaps..." -ForegroundColor Yellow
kubectl create configmap platform-db-init-scripts --from-file=init-platform-db.sql=backend/scripts/init-platform-db.sql -n ai-data --dry-run=client -o yaml | kubectl apply -f -
kubectl create configmap platform-db-usage-scripts --from-file=init-platform-db-usage.sql=backend/scripts/init-platform-db-usage.sql -n ai-data --dry-run=client -o yaml | kubectl apply -f -

# ── Step 3: Create Kong plugin & routing ConfigMaps ───────────────────────
Write-Host ""
Write-Host "[3/7] Creating Kong plugin & routing ConfigMaps..." -ForegroundColor Yellow
kubectl create configmap kong-plugin-simple-validator --from-file=gateway/plugins/simple-validator -n ai-gateway --dry-run=client -o yaml | kubectl apply -f -
kubectl create configmap kong-plugin-tenant-restriction --from-file=gateway/plugins/tenant-restriction -n ai-gateway --dry-run=client -o yaml | kubectl apply -f -
kubectl create configmap kong-deck-config --from-file=kong_final.yaml=gateway/kong_final.yaml -n ai-gateway --dry-run=client -o yaml | kubectl apply -f -
kubectl create configmap grafana-dashboards --from-file=monitoring/grafana/dashboards/ -n ai-monitoring --dry-run=client -o yaml | kubectl apply -f -
kubectl create configmap grafana-provisioning-dashboards --from-file=monitoring/grafana/provisioning/dashboards/ -n ai-monitoring --dry-run=client -o yaml | kubectl apply -f -
kubectl create configmap grafana-provisioning-datasources --from-file=monitoring/grafana/provisioning/datasources/ -n ai-monitoring --dry-run=client -o yaml | kubectl apply -f -

# ── Step 4: Create Configuration ConfigMaps ───────────────────────────────
Write-Host ""
Write-Host "[4/7] Creating Configuration ConfigMaps..." -ForegroundColor Yellow
kubectl create configmap keycloak-realm --from-file=realm-export.json=keycloak/realm-export.json -n ai-application --dry-run=client -o yaml | kubectl apply -f -
kubectl create configmap prometheus-config --from-file=prometheus.yml=monitoring/prometheus.yml -n ai-monitoring --dry-run=client -o yaml | kubectl apply -f -

# ── Step 5: Create Kong mTLS certificates (if not exists) ────────────────
Write-Host ""
Write-Host "[5/7] Checking Kong mTLS certificates..." -ForegroundColor Yellow
$certExists = kubectl get secret kong-cluster-certs -n ai-gateway 2>$null
if (-not $certExists) {
    Write-Host "  Generating new mTLS certificates..." -ForegroundColor Gray
    docker run --rm -v "${PWD}\k8s\secrets:/certs" alpine/openssl req -new -x509 -nodes -newkey rsa:2048 -keyout /certs/cluster.key -out /certs/cluster.crt -days 1095 -subj "/CN=kong_clustering"
    kubectl create secret tls kong-cluster-certs --cert=k8s/secrets/cluster.crt --key=k8s/secrets/cluster.key -n ai-gateway
} else {
    Write-Host "  Certificates already exist, skipping." -ForegroundColor Gray
}

# ── Step 6: Deploy everything via Kustomize ───────────────────────────────
Write-Host ""
Write-Host "[6/7] Deploying all services..." -ForegroundColor Yellow
$applyOutput = kubectl apply -k k8s/ 2>&1
$applyText = ($applyOutput | Out-String)
if ($applyText) {
    Write-Host $applyText
}
$applyExitCode = $LASTEXITCODE
if ($applyExitCode -ne 0) {
    throw "Step [6/7] failed: kubectl apply -k k8s/ returned exit code $applyExitCode"
}

# ── Wait for services ─────────────────────────────────────────────────────
Write-Host ""
Write-Host "Waiting for databases..." -ForegroundColor Gray
kubectl wait --for=condition=ready pod -l app=platform-db -n ai-data --timeout=180s
if ($LASTEXITCODE -ne 0) { throw "platform-db pods did not become ready in time." }
kubectl wait --for=condition=ready pod -l app=kong-db -n ai-data --timeout=180s
if ($LASTEXITCODE -ne 0) { throw "kong-db pods did not become ready in time." }

Write-Host "Waiting for application layer..." -ForegroundColor Gray
kubectl wait --for=condition=ready pod -l app=fastapi -n ai-application --timeout=240s
if ($LASTEXITCODE -ne 0) { throw "fastapi pods did not become ready in time." }
kubectl wait --for=condition=ready pod -l app=intent-classifier -n ai-application --timeout=240s
if ($LASTEXITCODE -ne 0) { throw "intent-classifier pods did not become ready in time." }
kubectl wait --for=condition=ready pod -l app=opa -n ai-application --timeout=120s
if ($LASTEXITCODE -ne 0) { throw "opa pods did not become ready in time." }

Write-Host "Waiting for gateway..." -ForegroundColor Gray
kubectl wait --for=condition=ready pod -l app=kong-cp -n ai-gateway --timeout=240s
if ($LASTEXITCODE -ne 0) {
    Write-Host "  Kong CP did not become ready; restarting control plane once..." -ForegroundColor Yellow
    kubectl rollout restart deployment/kong-cp -n ai-gateway
    kubectl rollout status deployment/kong-cp -n ai-gateway --timeout=240s
    if ($LASTEXITCODE -ne 0) { throw "kong-cp failed to become ready after restart." }
}

# ── Step 7: Sync Kong Configuration using Deck ────────────────────────────
Write-Host ""
Write-Host "[7/7] Synchronizing Kong Configuration..." -ForegroundColor Yellow
kubectl apply -f k8s/gateway/kong-deck-sync.yaml
if ($LASTEXITCODE -ne 0) { throw "Failed to create kong-deck-sync job." }
kubectl wait --for=condition=complete job/kong-deck-sync -n ai-gateway --timeout=180s
if ($LASTEXITCODE -ne 0) {
    Write-Host "  kong-deck-sync failed; dumping job logs..." -ForegroundColor Red
    kubectl logs job/kong-deck-sync -n ai-gateway --tail=200
    throw "kong-deck-sync job did not complete successfully."
}

# ── Final Status ──────────────────────────────────────────────────────────
Write-Host ""
Write-Host "==========================================" -ForegroundColor Green
Write-Host " Deployment Complete!" -ForegroundColor Green
Write-Host "==========================================" -ForegroundColor Green
Write-Host ""
Write-Host "Pod Status:" -ForegroundColor White
kubectl get pods -A
Write-Host ""
Write-Host "Next step: run  .\start-ui.ps1  to access the UI" -ForegroundColor Cyan
Write-Host ""
