"""Embedding helpers. The real model can't be downloaded in CI, so it is replaced by a fake with the same API."""
import sys
import types

import numpy as np
import pytest

from pipeline import embeddings


def test_document_embedding_is_normalised_and_768_dims():
    vec = embeddings.embed_document("APT28 used Mimikatz. " * 400, ["APT28 used Mimikatz."] * 400)
    assert len(vec) == 768
    assert abs(np.linalg.norm(vec) - 1.0) < 1e-5


def test_similar_texts_are_closer_than_unrelated_ones():
    a, b, c = embeddings.embed_texts(["APT28 used Mimikatz", "APT28 uses Mimikatz", "Quarterly sales grew"])
    assert np.dot(a, b) > np.dot(a, c)


def test_chunking_caps_huge_documents():
    chunks = embeddings.chunk_text("x", ["word " * 100] * 10_000)
    assert len(chunks) <= embeddings.DOC_MAX_CHUNKS


def _fake_st(dim):
    class FakeModel:
        def __init__(self, name, device=None):
            self.name = name

        def get_sentence_embedding_dimension(self):
            return dim

        def encode(self, texts, **kw):
            v = np.ones((len(texts), dim), dtype=np.float32)
            return v / np.linalg.norm(v, axis=1, keepdims=True)

    return types.SimpleNamespace(SentenceTransformer=FakeModel)


def test_sentence_transformer_backend(monkeypatch):
    monkeypatch.setitem(sys.modules, "sentence_transformers", _fake_st(768))
    emb = embeddings.SentenceTransformerEmbedder("BAAI/bge-base-en-v1.5")
    assert emb.dim == 768 and emb.encode(["a", "b"]).shape == (2, 768)


def test_wrong_model_dimension_fails_loudly(monkeypatch):
    monkeypatch.setitem(sys.modules, "sentence_transformers", _fake_st(384))
    with pytest.raises(RuntimeError, match="384"):
        embeddings.SentenceTransformerEmbedder("sentence-transformers/all-MiniLM-L6-v2")
