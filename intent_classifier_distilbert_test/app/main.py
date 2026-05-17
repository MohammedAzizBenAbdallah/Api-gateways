"""FastAPI app: POST /classify — DistilBERT test variant (mirrors production API)."""

from __future__ import annotations

import logging
import re
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from prometheus_fastapi_instrumentator import Instrumentator

from app.cache_layer import ClassificationCache
from app.config import settings
from app.nli_classifier import NLIClassifier
from app.schemas import ClassifyRequest, ClassifyResponse
from app.taxonomy import UNCLASSIFIED, load_taxonomy

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

_ws_re = re.compile(r"\s+")
_url_only_re = re.compile(r"https?://\S+$")


def normalize_text(text: str) -> str:
    t = text.strip().lower()
    return _ws_re.sub(" ", t)


def _resolve_taxonomy_path() -> str:
    p = Path(settings.taxonomy_path)
    if p.is_file():
        return str(p.resolve())
    # When run from repo root vs service dir
    alt = Path(__file__).resolve().parents[2] / "intent_taxonomy" / "intent_labels_v1.yaml"
    if alt.is_file():
        return str(alt)
    return settings.taxonomy_path


def _fallback_response(taxonomy_version: str, model_id: str) -> ClassifyResponse:
    return ClassifyResponse(
        intent_label=UNCLASSIFIED,
        confidence=0.0,
        source="fallback",
        taxonomy_version=taxonomy_version,
        model_id=model_id,
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    taxonomy_path = _resolve_taxonomy_path()
    taxonomy = load_taxonomy(taxonomy_path)
    app.state.taxonomy = taxonomy
    nli = NLIClassifier(
        taxonomy=taxonomy,
        model_name=settings.hf_zero_shot_model,
        hypothesis_template=settings.hypothesis_template,
        confidence_threshold=settings.confidence_threshold,
    )
    nli.load()
    app.state.nli_classifier = nli
    cache_labels = taxonomy.candidate_labels + taxonomy.nli_phrases
    app.state.cache = ClassificationCache(
        redis_url=settings.redis_url,
        redis_enabled=settings.redis_enabled,
        model_id=settings.hf_zero_shot_model,
        labels_tuple=cache_labels,
        fingerprint_hash=nli.fingerprint_hash,
        ttl_seconds=settings.cache_ttl_seconds,
        lru_max=settings.cache_max_entries,
    )
    await app.state.cache.connect()
    logger.info(
        "DistilBERT intent classifier ready (taxonomy v%s, model=%s, port=%s)",
        taxonomy.version,
        settings.hf_zero_shot_model,
        settings.port,
    )
    yield


app = FastAPI(title="Intent Classifier (DistilBERT test)", lifespan=lifespan)
Instrumentator().instrument(app).expose(app)


@app.get("/healthz")
async def healthz() -> dict:
    return {"status": "ok", "backend": "distilbert-nli"}


@app.get("/readyz")
async def readyz() -> dict:
    c = getattr(app.state, "nli_classifier", None)
    if c is None:
        raise HTTPException(status_code=503, detail="model not loaded")
    return {"status": "ready", "model_id": settings.hf_zero_shot_model}


@app.post("/classify", response_model=ClassifyResponse)
async def classify(body: ClassifyRequest) -> ClassifyResponse:
    text_raw = body.text.strip()
    text_norm = normalize_text(body.text)
    if (not text_raw) or (len(text_raw) < 3) or bool(_url_only_re.fullmatch(text_raw)):
        return _fallback_response(app.state.taxonomy.version, settings.hf_zero_shot_model)

    cached = await app.state.cache.get(text_norm, tenant_id=body.tenant_id)
    if cached is not None:
        return cached

    try:
        nli_result = await app.state.nli_classifier.classify(text_raw)
    except Exception as exc:
        logger.exception("Classification failed: %s", exc)
        return _fallback_response(app.state.taxonomy.version, settings.hf_zero_shot_model)

    intent = str(nli_result.get("intent", UNCLASSIFIED))
    if intent not in set(app.state.taxonomy.candidate_labels) | {UNCLASSIFIED}:
        logger.warning("Label not in taxonomy at HTTP layer: %s", intent)
        intent = UNCLASSIFIED

    response = ClassifyResponse(
        intent_label=intent,
        confidence=float(nli_result.get("confidence", 0.0)),
        source="model",
        taxonomy_version=app.state.taxonomy.version,
        model_id=settings.hf_zero_shot_model,
    )
    await app.state.cache.set(text_norm, response, tenant_id=body.tenant_id)
    return response
