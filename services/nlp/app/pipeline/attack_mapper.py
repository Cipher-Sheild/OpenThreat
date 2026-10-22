"""Phase 4: map behaviour sentences to MITRE ATT&CK techniques by meaning.

Two kinds of "anchors" are embedded once and cached:
  * the official technique text ("Parent: Name. Description")
  * labelled example sentences from MITRE CTID's TRAM dataset (Apache-2.0)
A sentence is embedded and compared with all anchors; each technique scores the best similarity
among its anchors. The top technique is returned when its score clears a threshold that was
calibrated on held-out TRAM documents (see evaluation/eval_attack.py).

Explicit technique IDs ("T1059.001") and exact technique names are still handled by NER and take
priority; this module catches behaviours described in plain words ("dumped credentials from LSASS").
"""
from __future__ import annotations

import hashlib
import json
import os
import threading
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from config import EMBEDDING_MODEL, RESOURCES_DIR
from pipeline.embeddings import get_embedder
from pipeline.gazetteer import get_gazetteer

# bge models retrieve better when the *query* carries this instruction (the anchors don't)
BGE_QUERY_PREFIX = "Represent this sentence for searching relevant passages: "


@dataclass
class TechniqueMatch:
    technique_id: str
    name: str
    score: float
    runner_up: str | None
    runner_up_score: float


class AttackMapper:
    def __init__(self, use_examples: bool = True, use_descriptions: bool = True,
                 exclude_example_docs: set[str] | None = None, cache_dir: str | None = None):
        self.gz = get_gazetteer()
        self.embedder = get_embedder()
        self.query_prefix = BGE_QUERY_PREFIX if "bge" in self.embedder.name.lower() else ""
        texts, labels = [], []
        if use_descriptions:
            for tid, t in self.gz.techniques_by_id.items():
                parent = self.gz.techniques_by_id.get(tid.split(".")[0]) if "." in tid else None
                name = f"{parent['name']}: {t['name']}" if parent else t["name"]
                texts.append(f"{name}. {t['description']}")
                labels.append(tid)
        if use_examples:
            examples = json.loads((RESOURCES_DIR / "tram_examples.json").read_text(encoding="utf-8"))["items"]
            for ex in examples:
                if exclude_example_docs and ex["doc"] in exclude_example_docs:
                    continue
                if ex["label"] in self.gz.techniques_by_id:
                    texts.append(ex["text"])
                    labels.append(ex["label"])
        self.labels = np.array(labels)
        self.vectors = self._embed_cached(texts, cache_dir)
        self.technique_ids = sorted(set(labels))
        self._tid_index = {t: i for i, t in enumerate(self.technique_ids)}
        self._anchor_tid = np.array([self._tid_index[l] for l in labels])

    def _embed_cached(self, texts: list[str], cache_dir: str | None) -> np.ndarray:
        key = hashlib.sha256((self.embedder.name + "\n".join(texts)).encode()).hexdigest()[:16]
        cache = Path(cache_dir or os.getenv("HF_HOME", "/tmp")) / f"attack_anchors_{key}.npy"
        if cache.exists():
            return np.load(cache)
        vecs = np.asarray(self.embedder.encode(texts), dtype=np.float32)
        try:
            cache.parent.mkdir(parents=True, exist_ok=True)
            np.save(cache, vecs)
        except OSError:
            pass
        return vecs

    def score_matrix(self, sentences: list[str]) -> np.ndarray:
        """(n_sentences, n_techniques) best anchor similarity per technique."""
        q = np.asarray(self.embedder.encode([self.query_prefix + s for s in sentences]), dtype=np.float32)
        sims = q @ self.vectors.T  # (n, anchors)
        out = np.full((len(sentences), len(self.technique_ids)), -1.0, dtype=np.float32)
        for t in range(len(self.technique_ids)):
            cols = self._anchor_tid == t
            out[:, t] = sims[:, cols].max(axis=1)
        return out

    def rank(self, sentences: list[str], k: int = 3) -> list[list[tuple[str, float]]]:
        scores = self.score_matrix(sentences)
        top = np.argsort(-scores, axis=1)[:, :k]
        return [[(self.technique_ids[j], float(scores[i, j])) for j in row] for i, row in enumerate(top)]

    def best(self, sentences: list[str]) -> list[TechniqueMatch]:
        out = []
        for ranked in self.rank(sentences, k=2):
            (tid, score), (tid2, score2) = ranked[0], ranked[1] if len(ranked) > 1 else (None, 0.0)
            out.append(TechniqueMatch(tid, self.gz.techniques_by_id[tid]["name"], score, tid2, score2))
        return out


_mapper = None
_lock = threading.Lock()


def get_attack_mapper() -> AttackMapper:
    global _mapper
    with _lock:
        if _mapper is None:
            _mapper = AttackMapper()
    return _mapper
