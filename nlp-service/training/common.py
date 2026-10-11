"""Shared helpers for training and evaluation: seeding, span-level NER metrics, confusion matrices,
and the experiment log (dataset version, model, hyper-parameters, seed, metrics) required for
reproducibility.
"""
from __future__ import annotations

import hashlib
import json
import os
import platform
import random
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

# Our v1 taxonomy (must match docs/contracts)
ENTITY_TYPES = ["THREAT_ACTOR", "MALWARE", "TOOL", "VULNERABILITY", "TECHNIQUE", "ORGANIZATION", "OBSERVABLE"]
NER_LABELS = ["O"] + [f"{p}-{t}" for t in ENTITY_TYPES for p in ("B", "I")]
RELATION_TYPES = ["USES", "DEPLOYS", "EXPLOITS", "TARGETS", "ATTRIBUTED_TO"]
RE_LABELS = ["NONE", *RELATION_TYPES, "OTHER"]


def set_seed(seed: int) -> None:
    random.seed(seed)
    np.random.seed(seed)
    os.environ["PYTHONHASHSEED"] = str(seed)
    try:
        import torch

        torch.manual_seed(seed)
        torch.cuda.manual_seed_all(seed)
    except ImportError:
        pass


def sha256_file(path: str | Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


# ---------------------------------------------------------------- span metrics (entity level)
def bio_to_spans(tags: list[str]) -> set[tuple[int, int, str]]:
    """BIO tags -> {(start, end_exclusive, type)}. A stray I- starts a new span (lenient, like seqeval)."""
    spans, start, etype = set(), None, None
    for i, tag in enumerate([*tags, "O"]):
        if tag == "O" or tag.startswith("B-") or (tag.startswith("I-") and tag[2:] != etype):
            if start is not None:
                spans.add((start, i, etype))
                start, etype = None, None
            if tag != "O":
                start, etype = i, tag[2:]
    return spans


def span_prf(gold: list[list[str]], pred: list[list[str]], types: list[str] = ENTITY_TYPES) -> dict:
    """Exact-match entity-level precision / recall / F1, per type plus micro and macro averages."""
    tp, fp, fn = Counter(), Counter(), Counter()
    for g, p in zip(gold, pred):
        gs, ps = bio_to_spans(g), bio_to_spans(p)
        for s in ps & gs:
            tp[s[2]] += 1
        for s in ps - gs:
            fp[s[2]] += 1
        for s in gs - ps:
            fn[s[2]] += 1
    return prf_table(tp, fp, fn, types)


def prf_table(tp: Counter, fp: Counter, fn: Counter, types: list[str]) -> dict:
    def prf(t, f_p, f_n):
        p = t / (t + f_p) if t + f_p else 0.0
        r = t / (t + f_n) if t + f_n else 0.0
        f = 2 * p * r / (p + r) if p + r else 0.0
        return {"precision": round(p, 4), "recall": round(r, 4), "f1": round(f, 4), "support": t + f_n}

    out = {t: prf(tp[t], fp[t], fn[t]) for t in types}
    out["micro"] = prf(sum(tp[t] for t in types), sum(fp[t] for t in types), sum(fn[t] for t in types))
    present = [t for t in types if out[t]["support"] > 0]
    out["macro"] = {
        k: round(float(np.mean([out[t][k] for t in present])), 4) if present else 0.0
        for k in ("precision", "recall", "f1")
    }
    out["macro"]["support"] = sum(out[t]["support"] for t in present)
    return out


def classification_prf(gold: list[str], pred: list[str], labels: list[str], positive: list[str]) -> dict:
    """Per-class P/R/F1 for single-label classification; micro/macro computed over `positive` classes only."""
    tp, fp, fn = Counter(), Counter(), Counter()
    for g, p in zip(gold, pred):
        if g == p:
            tp[g] += 1
        else:
            fp[p] += 1
            fn[g] += 1
    table = prf_table(tp, fp, fn, positive)
    for lab in labels:
        if lab not in table:
            table[lab] = prf_table(tp, fp, fn, [lab])[lab]
    table["accuracy"] = round(sum(tp.values()) / max(1, len(gold)), 4)
    return table


def confusion(gold: list[str], pred: list[str], labels: list[str]) -> list[list[int]]:
    idx = {l: i for i, l in enumerate(labels)}
    m = np.zeros((len(labels), len(labels)), dtype=int)
    for g, p in zip(gold, pred):
        if g in idx and p in idx:
            m[idx[g], idx[p]] += 1
    return m.tolist()


def plot_confusion(matrix: list[list[int]], labels: list[str], title: str, path: str | Path, normalize: bool = True) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    m = np.array(matrix, dtype=float)
    shown = m / np.maximum(m.sum(axis=1, keepdims=True), 1) if normalize else m
    fig, ax = plt.subplots(figsize=(1.1 * len(labels) + 2, 1.0 * len(labels) + 1.5))
    im = ax.imshow(shown, cmap="Blues", vmin=0, vmax=1 if normalize else None)
    ax.set_xticks(range(len(labels)), labels, rotation=45, ha="right")
    ax.set_yticks(range(len(labels)), labels)
    ax.set_xlabel("Predicted")
    ax.set_ylabel("Gold")
    ax.set_title(title)
    for i in range(len(labels)):
        for j in range(len(labels)):
            val = f"{shown[i, j]:.2f}" if normalize else f"{int(m[i, j])}"
            ax.text(j, i, val, ha="center", va="center", fontsize=8,
                    color="white" if shown[i, j] > (0.5 if normalize else shown.max() / 2) else "black")
    fig.colorbar(im, ax=ax, fraction=0.046)
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)


# ---------------------------------------------------------------- experiment log
def write_experiment_log(out_dir: str | Path, name: str, record: dict) -> Path:
    """Append-only reproducibility log: one JSON file per run, plus a running experiments.jsonl."""
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    record = {
        "experiment": name,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "python": platform.python_version(),
        **_lib_versions(),
        **record,
    }
    path = out_dir / f"{name}.json"
    path.write_text(json.dumps(record, indent=2))
    with open(out_dir / "experiments.jsonl", "a") as f:
        f.write(json.dumps(record) + "\n")
    return path


def _lib_versions() -> dict:
    out = {}
    for lib in ("torch", "transformers", "numpy"):
        try:
            out[f"{lib}_version"] = __import__(lib).__version__
        except ImportError:
            pass
    try:
        import torch

        out["device"] = torch.cuda.get_device_name(0) if torch.cuda.is_available() else "cpu"
    except ImportError:
        pass
    return out
