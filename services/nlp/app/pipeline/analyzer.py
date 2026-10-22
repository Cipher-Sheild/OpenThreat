"""Runs the whole /analyze pipeline and builds the contract (v1.1) response."""
from __future__ import annotations

from datetime import datetime, timezone

from config import (ATTACK_MIN_SIMILARITY, EMBEDDING_DIM, attack_semantic_enabled, MODEL_VERSION, NER_MIN_CONFIDENCE, NER_MODEL, RE_MAX_PAIRS_PER_SENTENCE,
                    RE_MIN_PROBABILITY, RE_MODEL, SCHEMA_VERSION)
from pipeline.attack_mapper import get_attack_mapper
from pipeline.behaviors import extract_behaviors
from pipeline.embeddings import embed_document, get_embedder
from pipeline.models import get_ner_model, get_re_model
from pipeline.ner import extract_entities
from pipeline.preprocess import Sentence, prepare
from pipeline.relations import extract_relations
from pipeline.temporal import extract_temporal


def _evidence(s: Sentence) -> dict:
    return {"text": s.text, "char_start": s.start, "char_end": s.end, "page_number": s.page_number}


def analyze(
    document_id: str,
    source_name: str,
    text: str | None = None,
    pages: list[tuple[int, str]] | None = None,
    source_url: str | None = None,
    published_at: str | None = None,
) -> dict:
    doc = prepare(text, pages)
    entities = extract_entities(doc, get_ner_model(NER_MODEL), NER_MIN_CONFIDENCE)
    relations = extract_relations(doc, entities, get_re_model(RE_MODEL), RE_MIN_PROBABILITY, RE_MAX_PAIRS_PER_SENTENCE)
    mapper = get_attack_mapper() if attack_semantic_enabled() else None
    behaviors = extract_behaviors(doc, entities, mapper, ATTACK_MIN_SIMILARITY)
    temporal = extract_temporal(doc, entities, published_at)
    embedding = embed_document(doc.text, [s.text for s in doc.sentences])

    return {
        "document_id": document_id,
        "source": {"name": source_name, "url": source_url, "published_at": published_at},
        "entities": [
            {
                "mention": e.mention,
                "canonical_name": e.canonical_name,
                "type": e.type,
                "subtype": e.subtype,
                "confidence": e.confidence,
                "char_start": e.char_start,
                "char_end": e.char_end,
                "page_number": e.page_number,
            }
            for e in entities
        ],
        "relations": [
            {
                "subject": r.subject.canonical_name,
                "subject_type": r.subject.type,
                "relation": r.relation,
                "object": r.object.canonical_name,
                "object_type": r.object.type,
                "negated": r.negated,
                "confidence": r.confidence,
                "evidence": _evidence(r.sentence),
            }
            for r in relations
        ],
        "behaviors": [
            {
                "description": b.description,
                "mitre_attack_id": b.mitre_attack_id,
                "mitre_attack_name": b.mitre_attack_name,
                "confidence": b.confidence,
                "evidence": _evidence(b.sentence),
            }
            for b in behaviors
        ],
        "temporal_events": [
            {
                "event": t.event,
                "entity": t.entity,
                "time": t.time,
                "type": t.type,
                "confidence": t.confidence,
                "evidence": _evidence(t.sentence),
            }
            for t in temporal
        ],
        "document_embedding": embedding,
        "novelty": [],  # novelty comes from /classify_novelty (needs candidate facts from the DB)
        "processing": {
            "model_version": MODEL_VERSION + (f" ner={NER_MODEL}" if NER_MODEL else "") + (f" re={RE_MODEL}" if RE_MODEL else ""),
            "processed_at": datetime.now(timezone.utc).isoformat(),
            "embedding_model": get_embedder().name,
            "embedding_dim": EMBEDDING_DIM,
        },
        "schema_version": SCHEMA_VERSION,
    }
