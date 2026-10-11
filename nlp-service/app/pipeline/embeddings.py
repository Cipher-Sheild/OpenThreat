"""Sentence / document embeddings.

Default: BAAI/bge-base-en-v1.5 via sentence-transformers (768 dims, L2-normalised, cosine).
The model downloads once into HF_HOME (mounted as nlp-service/model_cache in docker-compose).

EMBEDDING_BACKEND=hash gives a small deterministic stand-in (character n-gram hashing) with the
same dimension. It needs no download and is only meant for tests and offline development.
"""
from __future__ import annotations

import hashlib
import re
import threading

import numpy as np

from config import DOC_CHUNK_CHARS, DOC_MAX_CHUNKS, EMBEDDING_BACKEND, EMBEDDING_DIM, EMBEDDING_MODEL


class HashEmbedder:
    name = f"hash-ngram-{EMBEDDING_DIM}"
    dim = EMBEDDING_DIM

    def _features(self, text: str) -> list[str]:
        t = re.sub(r"\s+", " ", text.casefold()).strip()
        words = re.findall(r"\w+", t)
        feats = [f"w:{w}" for w in words] + [f"b:{a}_{b}" for a, b in zip(words, words[1:])]
        padded = f" {t} "
        feats += [f"c:{padded[i:i + 3]}" for i in range(len(padded) - 2)]
        return feats

    def encode(self, texts: list[str]) -> np.ndarray:
        out = np.zeros((len(texts), self.dim), dtype=np.float32)
        for i, text in enumerate(texts):
            for f in self._features(text):
                h = int.from_bytes(hashlib.blake2b(f.encode(), digest_size=8).digest(), "little")
                out[i, h % self.dim] += 1.0 if (h >> 63) & 1 else -1.0
        norms = np.linalg.norm(out, axis=1, keepdims=True)
        norms[norms == 0] = 1.0
        return out / norms


class SentenceTransformerEmbedder:
    def __init__(self, model_name: str):
        from sentence_transformers import SentenceTransformer  # heavy import, only when used

        self.model = SentenceTransformer(model_name, device="cpu")
        self.name = model_name
        self.dim = self.model.get_sentence_embedding_dimension()
        if self.dim != EMBEDDING_DIM:
            raise RuntimeError(
                f"{model_name} produces {self.dim}-dim vectors but EMBEDDING_DIM={EMBEDDING_DIM}. "
                "Qdrant is configured for EMBEDDING_DIM; change both together."
            )
        self._lock = threading.Lock()

    def encode(self, texts: list[str]) -> np.ndarray:
        with self._lock:
            return self.model.encode(texts, batch_size=32, normalize_embeddings=True, convert_to_numpy=True)


_embedder = None
_embedder_lock = threading.Lock()


def get_embedder():
    """Load the embedding model once (thread-safe: the startup warm-up and a request may race)."""
    global _embedder
    if _embedder is None:
        with _embedder_lock:
            if _embedder is None:
                _embedder = HashEmbedder() if EMBEDDING_BACKEND == "hash" else SentenceTransformerEmbedder(EMBEDDING_MODEL)
    return _embedder


def chunk_text(text: str, sentences: list[str] | None = None) -> list[str]:
    """Group sentences into ~DOC_CHUNK_CHARS chunks (the model only reads ~512 tokens at once)."""
    pieces = sentences if sentences else [text]
    chunks, current = [], ""
    for p in pieces:
        while len(p) > DOC_CHUNK_CHARS:  # one huge "sentence" (tables, lists)
            if current:
                chunks.append(current)
                current = ""
            chunks.append(p[:DOC_CHUNK_CHARS])
            p = p[DOC_CHUNK_CHARS:]
        if len(current) + len(p) + 1 > DOC_CHUNK_CHARS and current:
            chunks.append(current)
            current = p
        else:
            current = f"{current} {p}".strip()
    if current:
        chunks.append(current)
    if len(chunks) > DOC_MAX_CHUNKS:  # keep the start, the end and an even sample of the middle
        idx = np.linspace(0, len(chunks) - 1, DOC_MAX_CHUNKS).round().astype(int)
        chunks = [chunks[i] for i in sorted(set(idx))]
    return chunks


def embed_document(text: str, sentences: list[str] | None = None) -> list[float]:
    embedder = get_embedder()
    chunks = chunk_text(text, sentences)
    if not chunks:
        return [0.0] * embedder.dim
    vecs = embedder.encode(chunks)
    weights = np.array([len(c) for c in chunks], dtype=np.float32)[:, None]
    doc = (vecs * weights).sum(axis=0)
    norm = np.linalg.norm(doc)
    return (doc / norm if norm else doc).astype(float).tolist()


def embed_texts(texts: list[str]) -> list[list[float]]:
    return get_embedder().encode(texts).astype(float).tolist()
