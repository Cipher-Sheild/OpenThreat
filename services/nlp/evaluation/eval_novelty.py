"""Phase 5: novelty classification on the benchmark: full pipeline vs baselines, plus ablations.

For each benchmark item (old sentence, new sentence, gold label):
  full pipeline : /analyze old -> stored facts; /analyze new -> facts; /classify_novelty
  baselines     : keyword overlap, string similarity, embedding similarity of the two sentences
                  (they can only say KNOWN or NEW; thresholds tuned on the benchmark itself, which
                  favours the baselines)
  ablations     : the full pipeline with one component removed at a time
                  (entity resolution, relation semantics, temporal reasoning, negation)

    python evaluation/eval_novelty.py --out evaluation/results
"""
from __future__ import annotations

import argparse
import contextlib
import json
import re
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "app"))
sys.path.insert(0, str(ROOT / "training"))

from common import classification_prf, confusion, plot_confusion  # noqa: E402

LABELS = ["NEW", "KNOWN", "UPDATED", "CONFLICTING", "UNCERTAIN"]
PRIORITY = ["CONFLICTING", "UPDATED", "KNOWN", "NEW", "UNCERTAIN"]
STOP = set("the a an of to in on for by with and or was were is are has have had been be that this it its "
           "their they as at from into during against after over again also new latest".split())


def load_items(path: Path) -> list[dict]:
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]


# ---------------------------------------------------------------- full pipeline (with ablation switches)
@contextlib.contextmanager
def ablation(name: str):
    """Temporarily switch off one component of the pipeline."""
    import pipeline.novelty as nov
    import pipeline.resolution as res

    saved = {}

    def patch(mod, attr, value):
        saved[(mod, attr)] = getattr(mod, attr)
        setattr(mod, attr, value)

    if name == "no_entity_resolution":
        # names must match exactly (case-insensitive); no aliases, fuzzy or semantic matching
        patch(nov, "name_match_score",
              lambda a, b, aliases, t=None: 1.0 if a.strip().casefold() == b.strip().casefold() else 0.0)
    elif name == "no_relation_semantics":
        # relation types ignored: every fact is just "subject is linked to object", all multi-valued
        patch(nov, "SINGLE_VALUED_RELATIONS", set())
    elif name == "no_temporal":
        never = re.compile(r"(?!x)x")
        patch(nov, "TEMPORAL_NEGATION", never)
        patch(nov, "REVISION", never)
        patch(nov, "_parse_dt", lambda v: None)
    elif name == "no_negation":
        pass  # handled in run_pipeline (negated flags dropped)
    try:
        yield
    finally:
        for (mod, attr), value in saved.items():
            setattr(mod, attr, value)
        _ = res


def run_pipeline(items: list[dict], variant: str = "full") -> list[dict]:
    from pipeline.analyzer import analyze
    from pipeline.novelty import Candidate, Fact, classify

    preds = []
    with ablation(variant):
        for it in items:
            old = analyze("old-" + it["id"], "bench", it["old_text"], published_at=it["old_date"])
            new = analyze("new-" + it["id"], "bench", it["new_text"], published_at=it["new_date"])
            old_rel, new_rel = old["relations"], new["relations"]
            if variant == "no_relation_semantics":
                for r in old_rel + new_rel:
                    r["relation"] = "RELATED_TO"
            if variant == "no_negation":
                for r in old_rel + new_rel:
                    r["negated"] = False
            if variant == "no_entity_resolution":
                # undo the alias -> canonical normalisation done at extraction time as well
                for doc in (old, new):
                    by_canon = {}
                    for e in doc["entities"]:
                        by_canon.setdefault(e["canonical_name"], e["mention"])
                    for r in doc["relations"]:
                        r["subject"] = by_canon.get(r["subject"], r["subject"])
                        r["object"] = by_canon.get(r["object"], r["object"])
            cands = [Candidate(f"f{i}", r["subject"], r["relation"], r["object"], "ACTIVE", r["negated"],
                               first_seen_at=it["old_date"], last_seen_at=it["old_date"])
                     for i, r in enumerate(old_rel)]
            facts = [Fact(r["subject"], r["relation"], r["object"], r["confidence"], r["negated"],
                          r["subject_type"], r["object_type"], r["evidence"]) for r in new_rel]
            if not facts:
                label, detail = "UNCERTAIN", "no fact extracted from the new text (system abstains)"
            else:
                results = classify(facts, cands, it["new_date"])
                labels = [r.status for r in results]
                label = next(p for p in PRIORITY if p in labels)
                detail = "; ".join(f"{r.fact['subject']} {r.fact['relation']} {r.fact['object']}"
                                   f"{' (neg)' if r.fact.get('negated') else ''} -> {r.status}" for r in results)
            preds.append({"id": it["id"], "pred": label, "detail": detail,
                          "old_facts": [f"{r['subject']} {r['relation']} {r['object']}" for r in old_rel]})
    return preds


# ---------------------------------------------------------------- baselines (sentence level)
def _content(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9-]+", text.casefold()) if w not in STOP}


def keyword_scores(items):
    out = []
    for it in items:
        a, b = _content(it["old_text"]), _content(it["new_text"])
        out.append(len(a & b) / max(1, len(a | b)))
    return out


def string_scores(items):
    from rapidfuzz import fuzz

    return [fuzz.token_set_ratio(it["old_text"], it["new_text"]) / 100 for it in items]


def embedding_scores(items):
    from pipeline.embeddings import embed_texts

    vec = np.array(embed_texts([t for it in items for t in (it["old_text"], it["new_text"])]))
    return [float(vec[2 * i] @ vec[2 * i + 1]) for i in range(len(items))]


def threshold_baseline(scores, gold):
    """Pick the threshold (KNOWN if score >= t else NEW) that maximises macro-F1 on the benchmark."""
    best = None
    for t in sorted(set(np.round(scores, 3))):
        pred = ["KNOWN" if s >= t else "NEW" for s in scores]
        f1 = classification_prf(gold, pred, LABELS, LABELS)["macro"]["f1"]
        if best is None or f1 > best[0]:
            best = (f1, float(t), pred)
    return best[1], best[2]


# ---------------------------------------------------------------- main
def evaluate(gold, pred):
    m = classification_prf(gold, pred, LABELS, LABELS)
    return {"accuracy": m["accuracy"], "macro_f1": m["macro"]["f1"], "micro_f1": m["micro"]["f1"],
            "per_label": {l: m[l] for l in LABELS}}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", default=str(ROOT / "evaluation" / "data" / "novelty_benchmark.jsonl"))
    ap.add_argument("--out", default=str(ROOT / "evaluation" / "results"))
    args = ap.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    items = load_items(Path(args.data))
    gold = [it["gold"] for it in items]
    from pipeline.embeddings import get_embedder

    report = {"n_items": len(items), "gold_distribution": {l: gold.count(l) for l in LABELS},
              "embedding_model": get_embedder().name, "systems": {}, "ablations": {}}

    full = run_pipeline(items, "full")
    full_pred = [p["pred"] for p in full]
    report["systems"]["full_pipeline"] = evaluate(gold, full_pred)
    cm = confusion(gold, full_pred, LABELS)
    report["full_pipeline_confusion"] = {"labels": LABELS, "matrix": cm}
    plot_confusion(cm, LABELS, "Novelty classification - full pipeline", out / "confusion_novelty.png")
    plot_confusion(cm, LABELS, "Novelty classification - full pipeline (counts)", out / "confusion_novelty_counts.png",
                   normalize=False)

    for name, fn in (("keyword_overlap", keyword_scores), ("string_similarity", string_scores),
                     ("embedding_similarity", embedding_scores)):
        t, pred = threshold_baseline(fn(items), gold)
        report["systems"][name] = {**evaluate(gold, pred), "threshold": t}

    # fairer comparison: only the items whose gold label is KNOWN or NEW (all a baseline can output)
    sub = [i for i, g in enumerate(gold) if g in ("KNOWN", "NEW")]
    report["known_new_subset"] = {"n_items": len(sub)}
    for name, pred in [("full_pipeline", full_pred)] + [
        (n, threshold_baseline(fn([items[i] for i in sub]), [gold[i] for i in sub])[1])
        for n, fn in (("keyword_overlap", keyword_scores), ("string_similarity", string_scores),
                      ("embedding_similarity", embedding_scores))
    ]:
        p = [pred[i] for i in sub] if name == "full_pipeline" else pred
        m = classification_prf([gold[i] for i in sub], p, LABELS, ["KNOWN", "NEW"])
        report["known_new_subset"][name] = {"accuracy": m["accuracy"], "macro_f1": m["macro"]["f1"]}

    for variant in ("no_entity_resolution", "no_relation_semantics", "no_temporal", "no_negation"):
        pred = [p["pred"] for p in run_pipeline(items, variant)]
        m = evaluate(gold, pred)
        m["macro_f1_drop"] = round(report["systems"]["full_pipeline"]["macro_f1"] - m["macro_f1"], 4)
        report["ablations"][variant] = m

    # per-category accuracy of the full pipeline + error list (for the report's error analysis)
    cats = {}
    for it, p in zip(items, full):
        c = cats.setdefault(it["category"], [0, 0])
        c[0] += p["pred"] == it["gold"]
        c[1] += 1
    report["full_pipeline_per_category"] = {k: {"correct": v[0], "total": v[1], "accuracy": round(v[0] / v[1], 3)}
                                            for k, v in sorted(cats.items())}
    errors = [{**{k: it[k] for k in ("id", "category", "old_text", "new_text", "gold")}, "pred": p["pred"],
               "detail": p["detail"], "old_facts": p["old_facts"]}
              for it, p in zip(items, full) if p["pred"] != it["gold"]]
    (out / "novelty_errors.json").write_text(json.dumps(errors, indent=2))
    (out / "novelty_results.json").write_text(json.dumps(report, indent=2))

    print(f"{'system':<24}{'acc':>7}{'macroF1':>9}")
    for name, m in report["systems"].items():
        print(f"{name:<24}{m['accuracy']:>7.3f}{m['macro_f1']:>9.3f}")
    print("KNOWN/NEW subset:", {k: v for k, v in report["known_new_subset"].items()})
    print("ablations (macro-F1 drop):", {k: v["macro_f1_drop"] for k, v in report["ablations"].items()})


if __name__ == "__main__":
    main()
