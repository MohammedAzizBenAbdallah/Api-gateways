# Run DistilBERT test classifier locally on port 3011 (LRU cache only, no Redis).
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$Svc = Join-Path $Root "intent_classifier_distilbert_test"
Set-Location $Svc

if (-not (Test-Path ".venv")) {
    python -m venv .venv
}
& .\.venv\Scripts\pip.exe install -q -r requirements.txt

$env:PYTHONPATH = $Svc
$env:PORT = "3011"
$env:REDIS_ENABLED = "false"
$env:INTENT_TAXONOMY_PATH = (Join-Path $Root "intent_taxonomy\intent_labels_v1.yaml")
$env:HF_ZERO_SHOT_MODEL = "typeform/distilbert-base-uncased-mnli"
$env:HYPOTHESIS_TEMPLATE = "This is related to {}."
$env:INTENT_CONFIDENCE_THRESHOLD = "0.30"

Write-Host "Starting DistilBERT classifier on http://127.0.0.1:3011 (first start downloads model)..."
& .\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 3011
