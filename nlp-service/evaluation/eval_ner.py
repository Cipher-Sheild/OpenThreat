"""NER evaluation on the CyberNER test split (the same split train_ner.py uses).

Scores the service's extractor (rules only, or hybrid if --ner_model is given) at entity level,
so the Phase 2 rules and the Phase 3 model can be compared on exactly the same sentences.

    python evaluation/eval_ner.py --data cyberner_combined_stix.csv --out evaluation/results
    python evaluation/eval_ner.py --data ... --ner_model <hf-user>/openthreat-ner --tag hybrid
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "app"))
sys.path.insert(0, str(ROOT / "training"))

from common import ENTITY_TYPES, confusion, plot_confusion, span_prf  # noqa: E402
from data_ner import load_cyberner, split  # noqa: E402


def tags_from_entities(tokens: list[str], entities) -> list[str]:
    """Re-project character-level entities onto the dataset's tokens (text = tokens joined by spaces)."""
    starts, pos = [], 0
    for t in tokens:
        starts.append(pos)
        pos += len(t) + 1
    tags = ["O"] * len(tokens)
    for e in sorted(entities, key=lambda e: e.char_start):
        idx = [i for i, s in enumerate(starts) if s < e.char_end and e.char_start < s + len(tokens[i])]
        if not idx or any(tags[i] != "O" for i in idx):
            continue
        tags[idx[0]] = "B-" + e.type
        for i in idx[1:]:
            tags[i] = "I-" + e.type
    return tags


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", required=True)
    ap.add_argument("--out", default=str(ROOT / "evaluation" / "results"))
    ap.add_argument("--ner_model", default="")
    ap.add_argument("--tag", default="rules")
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()

    from config import NER_MIN_CONFIDENCE
    from pipeline.models import get_ner_model
    from pipeline.ner import extract_entities
    from pipeline.preprocess import PreparedDocument, Sentence as Sent

    model = get_ner_model(args.ner_model) if args.ner_model else None
    test = split(load_cyberner(args.data), seed=args.seed)["test"]
    gold, pred = [], []
    for s in test:
        text = " ".join(s.tokens)
        # each dataset sentence is one sentence for the extractor (no re-splitting)
        doc = PreparedDocument(text, [Sent(0, 0, len(text), text, None)], [])
        ents = [e for e in extract_entities(doc, model, NER_MIN_CONFIDENCE) if e.subtype != "coreference"]
        gold.append(s.tags)
        pred.append(tags_from_entities(s.tokens, ents))

    metrics = span_prf(gold, pred)
    per_source = {}
    for src in sorted({s.source for s in test}):
        idx = [i for i, s in enumerate(test) if s.source == src]
        per_source[src] = span_prf([gold[i] for i in idx], [pred[i] for i in idx])["micro"]
    flat_g = [t[2:] if t != "O" else "O" for row in gold for t in row]
    flat_p = [t[2:] if t != "O" else "O" for row in pred for t in row]
    labels = ENTITY_TYPES + ["O"]
    cm = confusion(flat_g, flat_p, labels)

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    plot_confusion(cm, labels, f"NER token confusion - {args.tag} (CyberNER test)", out / f"confusion_ner_{args.tag}.png")
    result = {"system": args.tag, "ner_model": args.ner_model or None, "n_sentences": len(test),
              "test": metrics, "test_per_source": per_source, "confusion_labels": labels, "confusion": cm}
    (out / f"ner_{args.tag}.json").write_text(json.dumps(result, indent=2))
    print(f"{args.tag}: micro P={metrics['micro']['precision']} R={metrics['micro']['recall']} F1={metrics['micro']['f1']}"
          f"  macro F1={metrics['macro']['f1']}")
    for t in ENTITY_TYPES:
        print(f"  {t:<14} P={metrics[t]['precision']:.3f} R={metrics[t]['recall']:.3f} F1={metrics[t]['f1']:.3f}")


if __name__ == "__main__":
    main()
