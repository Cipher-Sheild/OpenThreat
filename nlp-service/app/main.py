"""OpenThreat NLP Service (Member 1).

Endpoints (contract v1.1, see docs/contracts/):
  GET  /health            liveness + model info
  POST /analyze           document -> entities, relations, behaviours, temporal events, embedding
  POST /embed             texts -> 768-dim vectors
  POST /resolve           mentions + known DB entities -> which entity each mention is
  POST /classify_novelty  new facts + candidate DB facts -> NEW / KNOWN / UPDATED / CONFLICTING / UNCERTAIN
"""
import logging
import threading
from contextlib import asynccontextmanager
from dataclasses import asdict

from fastapi import FastAPI, HTTPException

from config import (attack_semantic_enabled, EMBEDDING_BACKEND, EMBEDDING_DIM, EMBEDDING_MODEL, MODEL_VERSION, NER_MODEL, RE_MODEL,
                    SCHEMA_VERSION)
from pipeline.analyzer import analyze
from pipeline.attack_mapper import get_attack_mapper
from pipeline.embeddings import embed_texts, get_embedder
from pipeline.gazetteer import get_gazetteer
from pipeline.models import get_ner_model, get_re_model
from pipeline.novelty import Candidate, Fact, classify
from pipeline.resolution import KnownEntity, resolve
from schemas import (
    AnalyzeRequest,
    AnalyzeResponse,
    ClassifyNoveltyRequest,
    ClassifyNoveltyResponse,
    EmbedRequest,
    EmbedResponse,
    ResolveRequest,
    ResolveResponse,
)

log = logging.getLogger("uvicorn.error")
readiness = {'ready': False, 'error': None}


@asynccontextmanager
async def lifespan(_: FastAPI):
    # Load gazetteers and the embedding model in the background at startup, so the first
    # /analyze call from the platform doesn't wait for a model download.
    def warm():
        try:
            get_gazetteer()
            get_embedder().encode(["warm-up"])
            get_ner_model(NER_MODEL)
            get_re_model(RE_MODEL)
            if attack_semantic_enabled():
                get_attack_mapper()  # embeds ~6k ATT&CK anchors once (cached in the model folder)
            log.info("NLP models loaded (%s)", get_embedder().name)
            readiness.update(ready=True, error=None)
        except Exception:  # noqa: BLE001 - the endpoint will report the real error
            log.exception("model warm-up failed")
            readiness.update(ready=False, error='Model loading failed; inspect NLP logs.')

    threading.Thread(target=warm, daemon=True).start()
    yield


app = FastAPI(
    lifespan=lifespan,
    title="OpenThreat NLP Service",
    version=MODEL_VERSION,
    description="Member 1's NLP & Intelligence Engine. Contract: docs/contracts/nlp_output_schema.json (v1.1).",
)


@app.get("/health")
def health_check():
    return {
        "status": "ok" if readiness['ready'] else ('error' if readiness['error'] else 'warming'),
        "ready": readiness['ready'],
        "error": readiness['error'],
        "service": "nlp-service",
        "model_version": MODEL_VERSION,
        "schema_version": SCHEMA_VERSION,
        "embedding_backend": EMBEDDING_BACKEND,
        "embedding_model": EMBEDDING_MODEL if EMBEDDING_BACKEND != "hash" else "hash",
        "embedding_dim": EMBEDDING_DIM,
        "ner_model": NER_MODEL or "rules",
        "re_model": RE_MODEL or "rules",
    }


@app.post("/analyze", response_model=AnalyzeResponse)
def analyze_document(req: AnalyzeRequest):
    pages = [(p.page_number, p.text) for p in req.pages] if req.pages else None
    try:
        return analyze(req.document_id, req.source_name, req.text, pages, req.source_url, req.published_at)
    except RuntimeError as exc:  # e.g. embedding model / dimension problems
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.post("/embed", response_model=EmbedResponse)
def embed(req: EmbedRequest):
    embedder = get_embedder()
    return {"model": embedder.name, "dim": embedder.dim, "embeddings": embed_texts(req.texts)}


@app.post("/resolve", response_model=ResolveResponse)
def resolve_mentions(req: ResolveRequest):
    known = [KnownEntity(k.entity_id, k.canonical_name, k.type, list(k.aliases)) for k in req.known_entities]
    return {"results": [asdict(resolve(m.mention, m.type, known)) for m in req.mentions]}


@app.post("/classify_novelty", response_model=ClassifyNoveltyResponse)
def classify_novelty(req: ClassifyNoveltyRequest):
    facts = [
        Fact(
            subject=f.subject, relation=f.relation, object=f.object, confidence=f.confidence, negated=f.negated,
            subject_type=f.subject_type, object_type=f.object_type, evidence=f.evidence,
            raw=f.model_dump(exclude_none=True),
        )
        for f in req.facts
    ]
    candidates = [Candidate(**c.model_dump()) for c in req.candidates]
    return {"results": [asdict(r) for r in classify(facts, candidates, req.published_at)]}
