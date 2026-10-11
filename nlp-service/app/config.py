"""Service settings. Everything can be overridden with environment variables."""
import os
from pathlib import Path

RESOURCES_DIR = Path(__file__).resolve().parent / "resources"

SCHEMA_VERSION = "1.1"
# Phase 3 trained models (Hugging Face repo id or local folder). Empty = rule-based extraction only.
NER_MODEL = os.getenv("NER_MODEL", "")
RE_MODEL = os.getenv("RE_MODEL", "")
NER_MIN_CONFIDENCE = float(os.getenv("NER_MIN_CONFIDENCE", "0.50"))
RE_MIN_PROBABILITY = float(os.getenv("RE_MIN_PROBABILITY", "0.50"))
RE_MAX_PAIRS_PER_SENTENCE = int(os.getenv("RE_MAX_PAIRS_PER_SENTENCE", "60"))

_mode = "hybrid" if (NER_MODEL or RE_MODEL) else "rules"
MODEL_VERSION = os.getenv("MODEL_VERSION", f"{_mode}-0.3.0")

# Embeddings
# "sentence-transformers" = real model (downloads once into HF_HOME, i.e. the mounted model_cache)
# "hash" = tiny deterministic stand-in, no download; for tests and offline work only
EMBEDDING_BACKEND = os.getenv("EMBEDDING_BACKEND", "sentence-transformers")
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "BAAI/bge-base-en-v1.5")
EMBEDDING_DIM = int(os.getenv("EMBEDDING_DIM", "768"))
DOC_CHUNK_CHARS = int(os.getenv("DOC_CHUNK_CHARS", "1500"))
DOC_MAX_CHUNKS = int(os.getenv("DOC_MAX_CHUNKS", "128"))

# Relation extraction
REL_MAX_GAP_CHARS = int(os.getenv("REL_MAX_GAP_CHARS", "160"))

# Entity resolution thresholds (0-1)
RESOLVE_FUZZY_ACCEPT = float(os.getenv("RESOLVE_FUZZY_ACCEPT", "0.85"))
RESOLVE_SEMANTIC_ACCEPT = float(os.getenv("RESOLVE_SEMANTIC_ACCEPT", "0.85"))
# A match scoring below this is "accepted but not sure": novelty returns UNCERTAIN (policy rule 5)
RESOLVE_CONFIDENT = float(os.getenv("RESOLVE_CONFIDENT", "0.90"))

# Novelty
NOVELTY_MIN_FACT_CONFIDENCE = float(os.getenv("NOVELTY_MIN_FACT_CONFIDENCE", "0.50"))
# Relations where one subject can only have one object at a time.
# A different object from a newer source = UPDATED; otherwise CONFLICTING.
SINGLE_VALUED_RELATIONS = set(
    os.getenv("SINGLE_VALUED_RELATIONS", "ATTRIBUTED_TO").split(",")
)

# Phase 4: semantic ATT&CK mapping of behaviour sentences (needs the real embedding model).
# "auto" = on with sentence-transformers, off with the hash test embedder.
ATTACK_SEMANTIC = os.getenv("ATTACK_SEMANTIC", "auto")
ATTACK_MIN_SIMILARITY = float(os.getenv("ATTACK_MIN_SIMILARITY", "0.64"))  # best F1 on held-out TRAM (evaluation/eval_attack.py)


def attack_semantic_enabled() -> bool:
    if ATTACK_SEMANTIC == "auto":
        return EMBEDDING_BACKEND != "hash"
    return ATTACK_SEMANTIC.lower() in ("1", "true", "on", "yes")
