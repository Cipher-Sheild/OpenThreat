"""Temporal extraction on a small hand-labelled sanity set (30 sentences, published 2024-06-20).

Gold = what an analyst would record: (entity, event type, ISO time). Scored at event level
(all three must match) and time-only (entity + time). Includes hard cases on purpose: ranges,
"second half of", "mid-2023", seasons.

    python evaluation/eval_temporal.py --out evaluation/results
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "app"))

PUB = "2024-06-20T00:00:00Z"
CASES = [
    ("Microsoft patched CVE-2023-23397 in March 2023.", [("CVE-2023-23397", "PATCHED", "2023-03")]),
    ("CVE-2021-44228 was disclosed on 9 December 2021.", [("CVE-2021-44228", "DISCLOSED", "2021-12-09")]),
    ("Ivanti disclosed CVE-2024-21887 on January 10, 2024.", [("CVE-2024-21887", "DISCLOSED", "2024-01-10")]),
    ("APT28 has been active since 2004.", [("APT28", "ACTIVE", "2004")]),
    ("Emotet was first observed in 2014.", [("Emotet", "FIRST_SEEN", "2014")]),
    ("Law enforcement took down the Emotet botnet in January 2021.", [("Emotet", "RETIRED", "2021-01")]),
    ("LockBit was disrupted in February 2024 by an international operation.", [("LockBit", "RETIRED", "2024-02")]),
    ("HeadLace, a backdoor, was first seen in September 2023.", [("HeadLace", "FIRST_SEEN", "2023-09")]),
    ("Qakbot was dismantled last year.", [("QakBot", "RETIRED", "2023")]),
    ("APT29 was first observed three months ago targeting diplomats.", [("APT29", "FIRST_SEEN", "2024-03")]),
    ("The Rhysida ransomware emerged in May 2023.", [("Rhysida", "FIRST_SEEN", "2023-05")]),
    ("Sandworm Team attacked the Ukrainian grid in December 2015.", [("Sandworm Team", "OBSERVED", "2015-12")]),
    ("CVE-2023-34362 was disclosed in May 2023 and patched in June 2023.",
     [("CVE-2023-34362", "DISCLOSED", "2023-05"), ("CVE-2023-34362", "PATCHED", "2023-06")]),
    ("In March 2024, Microsoft patched CVE-2024-21412.", [("CVE-2024-21412", "PATCHED", "2024-03")]),
    ("Lazarus Group has been operating since 2009.", [("Lazarus Group", "ACTIVE", "2009")]),
    ("FIN7 was active from 2015 to 2023.", [("FIN7", "ACTIVE", "2015"), ("FIN7", "ACTIVE", "2023")]),
    ("BlackCat went offline in March 2024 after an exit scam.", [("BlackCat", "RETIRED", "2024-03")]),
    ("Volt Typhoon has been active since at least mid-2021.", [("Volt Typhoon", "ACTIVE", "2021")]),
    ("Turla deployed Kazuar in Q3 2023.", [("Turla", "OBSERVED", "2023-07")]),
    ("Akira ransomware first appeared in March 2023.", [("Akira", "FIRST_SEEN", "2023-03")]),
    ("Citrix patched CVE-2023-4966 on 10 October 2023.", [("CVE-2023-4966", "PATCHED", "2023-10-10")]),
    ("APT41 resumed operations earlier this year.", [("APT41", "OBSERVED", "2024")]),
    ("The Hive ransomware infrastructure was seized in January 2023.", [("Hive", "RETIRED", "2023-01")]),
    ("Kimsuky was observed using a new backdoor last month.", [("Kimsuky", "OBSERVED", "2024-05")]),
    ("APT33 targeted aviation firms during the second half of 2023.", [("APT33", "OBSERVED", "2023-07")]),
    ("CVE-2024-3400 was reported in April 2024.", [("CVE-2024-3400", "DISCLOSED", "2024-04")]),
    ("Fortinet fixed CVE-2023-27997 in June 2023.", [("CVE-2023-27997", "PATCHED", "2023-06")]),
    ("Cobalt Strike was first seen in attacks in 2012.", [("Cobalt Strike", "FIRST_SEEN", "2012")]),
    ("Wizard Spider ceased deploying Ryuk in 2021.", [("Ryuk", "RETIRED", "2021")]),
    ("APT28 exploited CVE-2023-23397 between April and December 2022.", [("APT28", "OBSERVED", "2022-04"), ("APT28", "OBSERVED", "2022-12")]),
]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(ROOT / "evaluation" / "results"))
    args = ap.parse_args()
    from pipeline.analyzer import analyze

    tp = fp = fn = tp_time = 0
    rows = []
    for i, (text, gold) in enumerate(CASES):
        pred = {(e["entity"], e["type"], e["time"]) for e in analyze(f"t{i}", "bench", text, published_at=PUB)["temporal_events"]}
        g = set(gold)
        tp += len(pred & g)
        fp += len(pred - g)
        fn += len(g - pred)
        tp_time += len({(e, t) for e, _, t in pred} & {(e, t) for e, _, t in g})
        rows.append({"text": text, "gold": sorted(g), "pred": sorted(pred), "correct": pred == g})
    p, r = tp / max(1, tp + fp), tp / max(1, tp + fn)
    n_gold = sum(len(g) for _, g in CASES)
    result = {"n_sentences": len(CASES), "n_gold_events": n_gold,
              "event_level": {"precision": round(p, 4), "recall": round(r, 4),
                              "f1": round(2 * p * r / (p + r), 4) if p + r else 0.0},
              "entity_time_recall": round(tp_time / n_gold, 4),
              "sentences_fully_correct": sum(x["correct"] for x in rows), "details": rows}
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "temporal_results.json").write_text(json.dumps(result, indent=2))
    print(json.dumps({k: v for k, v in result.items() if k != "details"}, indent=1))


if __name__ == "__main__":
    main()
