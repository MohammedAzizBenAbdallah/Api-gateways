"""FastAPI app: POST /classify, health probes, Prometheus metrics."""

from __future__ import annotations

import logging
import re
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from prometheus_fastapi_instrumentator import Instrumentator

from app.cache_layer import ClassificationCache
from app.config import settings
from app.llm_classifier import LLMClassifier
from app.schemas import ClassifyRequest, ClassifyResponse
from app.taxonomy import UNCLASSIFIED, load_taxonomy

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

_ws_re = re.compile(r"\s+")
_url_only_re = re.compile(r"https?://\S+$")


def normalize_text(text: str) -> str:
    t = text.strip().lower()
    return _ws_re.sub(" ", t)


def _fallback_response(taxonomy_version: str) -> ClassifyResponse:
    return ClassifyResponse(
        intent_label=UNCLASSIFIED,
        confidence=0.0,
        source="fallback",
        taxonomy_version=taxonomy_version,
        model_id=settings.llm_model,
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    taxonomy = load_taxonomy(settings.taxonomy_path)
    app.state.taxonomy = taxonomy
    app.state.llm_classifier = LLMClassifier(
        taxonomy=taxonomy,
        base_url=settings.llm_base_url,
        model_name=settings.llm_model,
        timeout_seconds=settings.llm_timeout_seconds,
    )
    cache_labels = taxonomy.candidate_labels + taxonomy.nli_phrases
    app.state.cache = ClassificationCache(
        redis_url=settings.redis_url,
        model_id=settings.llm_model,
        labels_tuple=cache_labels,
        system_instruction_hash=app.state.llm_classifier.system_instruction_hash,
        ttl_seconds=settings.cache_ttl_seconds,
        lru_max=settings.cache_max_entries,
    )
    await app.state.cache.connect()
    logger.info("Intent classifier ready (taxonomy v%s)", taxonomy.version)
    yield
    await app.state.llm_classifier.close()
    await app.state.cache.close()


app = FastAPI(title="Intent Classifier", lifespan=lifespan)
Instrumentator().instrument(app).expose(app)


@app.get("/healthz")
async def healthz() -> dict:
    return {"status": "ok"}


@app.get("/readyz")
async def readyz() -> dict:
    c = getattr(app.state, "llm_classifier", None)
    if c is None:
        raise HTTPException(status_code=503, detail="model not loaded")
    return {"status": "ready"}


@app.post("/classify", response_model=ClassifyResponse)
async def classify(body: ClassifyRequest) -> ClassifyResponse:
    text_raw = body.text.strip()
    text_norm = normalize_text(body.text)
    # Degenerate-input pre-filter: skip LLM for empty / too short / bare URL-only text.
    if (not text_raw) or (len(text_raw) < 3) or bool(_url_only_re.fullmatch(text_raw)):
        return _fallback_response(app.state.taxonomy.version)

    cached = await app.state.cache.get(text_norm, tenant_id=body.tenant_id)
    if cached is not None:
        return cached

    try:
        llm_result = await app.state.llm_classifier.classify(text_raw)
    except Exception as exc:
        logger.exception("Classification failed: %s", exc)
        return _fallback_response(app.state.taxonomy.version)

    intent = str(llm_result.get("intent", UNCLASSIFIED))
    if intent not in set(app.state.taxonomy.candidate_labels) | {UNCLASSIFIED}:
        logger.warning("Label not in taxonomy at HTTP layer: %s", intent)
        intent = UNCLASSIFIED

    response = ClassifyResponse(
        intent_label=intent,
        confidence=float(llm_result.get("confidence", 0.0)),
        source="model",
        taxonomy_version=app.state.taxonomy.version,
        model_id=settings.llm_model,
    )
    await app.state.cache.set(text_norm, response, tenant_id=body.tenant_id)
    return response
