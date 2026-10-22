"""Phase 4 evaluation: semantic ATT&CK mapping.

Test sets
  * TRAM held-out: sentences from 30 TRAM documents never used as anchors (document-level split,
    evaluation/data/tram_split.json), 50 technique labels.
  * CTI-HAL: 974 annotated passages from 81 real reports (out-of-domain, 175 techniques, multi-label).
Variants: anchors = technique descriptions only / TRAM examples only / both.
Metrics: top-1 and top-3 accuracy (exact ID, and parent technique), and a precision/recall
trade-off using 1,000 TRAM negative sentences, which gives the recommended ATTACK_MIN_SIMILARITY.

    python evaluation/eval_attack.py --out evaluation/results
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "evaluation" / "data"
sys.path.insert(0, str(ROOT / "app"))


def topk_metrics(ranked: list[list[tuple[str, float]]], gold: list[set[str]]) -> dict:
    def parent(t):
        return t.split(".")[0]

    out = {}
    for k in (1, 3):
        exact = np.mean([any(t in g for t, _ in r[:k]) for r, g in zip(ranked, gold)])
        par = np.mean([any(parent(t) in {parent(x) for x in g} for t, _ in r[:k]) for r, g in zip(ranked, gold)])
        out[f"top{k}_exact"] = round(float(exact), 4)
        out[f"top{k}_parent"] = round(float(par), 4)
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(ROOT / "evaluation" / "results"))
    args = ap.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    from pipeline.attack_mapper import AttackMapper
    from pipeline.embeddings import get_embedder

    tram = json.loads((ROOT / "app" / "resources" / "tram_examples.json").read_text())["items"]
    test_docs = set(json.loads((DATA / "tram_split.json").read_text())["test_docs"])
    tram_test = [x for x in tram if x["doc"] in test_docs]
    ctihal = json.loads((DATA / "ctihal_attack.json").read_text())
    negatives = json.loads((DATA / "tram_negatives_sample.json").read_text())

    report = {"embedding_model": get_embedder().name, "n_tram_test": len(tram_test), "n_ctihal": len(ctihal),
              "n_negatives": len(negatives), "variants": {}}
    for variant, kw in (("descriptions_only", dict(use_examples=False)),
                        ("examples_only", dict(use_descriptions=False)),
                        ("descriptions_and_examples", dict())):
        mapper = AttackMapper(exclude_example_docs=test_docs, **kw)
        r_tram = mapper.rank([x["text"] for x in tram_test], k=3)
        r_hal = mapper.rank([x["text"] for x in ctihal], k=3)
        report["variants"][variant] = {
            "tram_heldout": topk_metrics(r_tram, [{x["label"]} for x in tram_test]),
            "ctihal": topk_metrics(r_hal, [set(x["labels"]) for x in ctihal]),
        }
        print(variant, json.dumps(report["variants"][variant]))

        if variant == "descriptions_and_examples":
            # precision / recall vs threshold (positives: TRAM held-out, negatives: no-technique sentences)
            neg_scores = [r[0][1] for r in mapper.rank(negatives, k=1)]
            pos = [(r[0][1], r[0][0] == x["label"]) for r, x in zip(r_tram, tram_test)]
            curve, best = [], None
            for t in np.round(np.arange(0.30, 0.96, 0.01), 2):
                tp = sum(1 for s, ok in pos if s >= t and ok)
                fp = sum(1 for s, ok in pos if s >= t and not ok) + sum(1 for s in neg_scores if s >= t)
                p = tp / (tp + fp) if tp + fp else 0.0
                rcl = tp / len(pos)
                f1 = 2 * p * rcl / (p + rcl) if p + rcl else 0.0
                curve.append({"threshold": float(t), "precision": round(p, 4), "recall": round(rcl, 4), "f1": round(f1, 4)})
                if best is None or f1 > best["f1"]:
                    best = curve[-1]
            report["threshold_curve"] = curve
            report["recommended_threshold"] = best
            _plot(curve, out / "attack_threshold_curve.png", best)

    (out / "attack_results.json").write_text(json.dumps(report, indent=2))
    print("recommended ATTACK_MIN_SIMILARITY:", report["recommended_threshold"])


def _plot(curve, path, best):
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    t = [c["threshold"] for c in curve]
    fig, ax = plt.subplots(figsize=(6, 4))
    for key in ("precision", "recall", "f1"):
        ax.plot(t, [c[key] for c in curve], label=key)
    ax.axvline(best["threshold"], ls="--", c="grey")
    ax.set_xlabel("similarity threshold")
    ax.set_title("ATT&CK mapping: precision/recall vs threshold")
    ax.legend()
    fig.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)


if __name__ == "__main__":
    main()
