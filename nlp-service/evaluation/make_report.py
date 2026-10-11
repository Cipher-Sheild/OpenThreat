"""Fill the result tables of the NLP report draft from the evaluation outputs.

    python evaluation/make_report.py --results evaluation/results --colab colab_results \
        --out docs/report_nlp_draft.md

--results : folder produced by evaluation/run_all.py (unzipped results.zip)
--colab   : folder produced by the Colab notebook (unzipped openthreat_results.zip)
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TYPES = ["THREAT_ACTOR", "MALWARE", "TOOL", "VULNERABILITY", "TECHNIQUE", "ORGANIZATION", "OBSERVABLE"]
RELS = ["USES", "DEPLOYS", "EXPLOITS", "TARGETS", "ATTRIBUTED_TO"]
LABELS = ["NEW", "KNOWN", "UPDATED", "CONFLICTING", "UNCERTAIN"]


def load(path: Path):
    return json.loads(path.read_text()) if path.exists() else None


def f(x):
    return "–" if x is None else f"{x:.3f}"


def ner_table(cols: dict[str, dict | None]) -> str:
    names = [n for n, m in cols.items() if m]
    head = "| Entity type | " + " | ".join(f"{n} P / R / F1" for n in names) + " | Support |\n"
    head += "|---|" + "---|" * len(names) + "---|\n"
    rows = []
    for t in TYPES + ["micro", "macro"]:
        cells = [f"{f(cols[n][t]['precision'])} / {f(cols[n][t]['recall'])} / **{f(cols[n][t]['f1'])}**" for n in names]
        support = next(cols[n][t].get("support") for n in names)
        rows.append(f"| {t} | " + " | ".join(cells) + f" | {support} |")
    return head + "\n".join(rows)


def build(results: Path, colab: Path) -> dict[str, str]:
    out = {}
    ner_rules = load(results / "ner_rules.json")
    ner_hybrid = load(results / "ner_hybrid.json")
    ner_model = load(colab / "ner" / "metrics_ner.json")
    out["NER_TABLE"] = ner_table({
        "Rules (Phase 2)": ner_rules and ner_rules["test"],
        "Fine-tuned model": ner_model and ner_model["test"],
        "Hybrid (deployed)": ner_hybrid and ner_hybrid["test"],
    })
    if ner_model:
        d = ner_model["data"]
        out["NER_DATA"] = (f"train {d['train']['sentences']:,} / dev {d['dev']['sentences']:,} / test "
                           f"{d['test']['sentences']:,} sentences; {d['train']['tokens'] + d['dev']['tokens'] + d['test']['tokens']:,} tokens")
        out["NER_PER_SOURCE"] = "| Source | P | R | F1 |\n|---|---|---|---|\n" + "\n".join(
            f"| {s} | {f(m['precision'])} | {f(m['recall'])} | {f(m['f1'])} |" for s, m in ner_model["test_per_source"].items())

    re_m = load(colab / "re" / "metrics_re.json")
    if re_m:
        t = re_m["test"]
        out["RE_TABLE"] = "| Relation | P | R | F1 | Support |\n|---|---|---|---|---|\n" + "\n".join(
            f"| {r} | {f(t[r]['precision'])} | {f(t[r]['recall'])} | **{f(t[r]['f1'])}** | {t[r]['support']} |"
            for r in RELS + ["micro", "macro"]) + f"\n\nAccuracy over all 7 classes (incl. NONE / OTHER): {f(t['accuracy'])}"
        out["RE_DATA"] = json.dumps({k: v for k, v in re_m["data"].items() if k != "skipped"})

    att = load(results / "attack_results.json")
    if att:
        rows = []
        for v, m in att["variants"].items():
            rows.append(f"| {v.replace('_', ' ')} | {f(m['tram_heldout']['top1_exact'])} | {f(m['tram_heldout']['top3_exact'])} | "
                        f"{f(m['ctihal']['top1_exact'])} | {f(m['ctihal']['top1_parent'])} | {f(m['ctihal']['top3_exact'])} |")
        out["ATTACK_TABLE"] = ("| Anchors | TRAM held-out top-1 | TRAM top-3 | CTI-HAL top-1 | CTI-HAL top-1 (parent) | CTI-HAL top-3 |\n"
                               "|---|---|---|---|---|---|\n" + "\n".join(rows))
        b = att["recommended_threshold"]
        out["ATTACK_THRESHOLD"] = (f"similarity ≥ {b['threshold']:.2f} (precision {b['precision']:.3f}, recall {b['recall']:.3f}, "
                                   f"F1 {b['f1']:.3f}; {att['n_tram_test']} held-out positives, {att['n_negatives']} negatives)")
        out["EMBEDDING_MODEL"] = att["embedding_model"]

    tmp = load(results / "temporal_results.json")
    if tmp:
        e = tmp["event_level"]
        out["TEMPORAL"] = (f"{tmp['n_sentences']} sentences / {tmp['n_gold_events']} gold events: event-level P {f(e['precision'])}, "
                           f"R {f(e['recall'])}, F1 **{f(e['f1'])}**; entity+time recall {f(tmp['entity_time_recall'])}; "
                           f"{tmp['sentences_fully_correct']}/{tmp['n_sentences']} sentences fully correct")

    for tag in ("rules", "hybrid"):
        nov = load(results / tag / "novelty_results.json")
        if not nov:
            continue
        sysrows = [f"| {n.replace('_', ' ')} | {f(m['accuracy'])} | **{f(m['macro_f1'])}** | "
                   + " | ".join(f(m["per_label"][l]["f1"]) for l in LABELS) + " |" for n, m in nov["systems"].items()]
        out[f"NOVELTY_{tag.upper()}"] = ("| System | Accuracy | Macro-F1 | " + " | ".join(f"F1 {l}" for l in LABELS) + " |\n"
                                         "|---|---|---|" + "---|" * len(LABELS) + "\n" + "\n".join(sysrows))
        kn = nov["known_new_subset"]
        out[f"KNOWNNEW_{tag.upper()}"] = (f"KNOWN/NEW subset ({kn['n_items']} items): " + "; ".join(
            f"{k.replace('_', ' ')} acc {f(v['accuracy'])}" for k, v in kn.items() if k != "n_items"))
        out[f"ABLATION_{tag.upper()}"] = ("| Removed component | Accuracy | Macro-F1 | Drop |\n|---|---|---|---|\n"
                                          f"| (none: full pipeline) | {f(nov['systems']['full_pipeline']['accuracy'])} | "
                                          f"{f(nov['systems']['full_pipeline']['macro_f1'])} | – |\n" + "\n".join(
            f"| {k.replace('no_', '').replace('_', ' ')} | {f(v['accuracy'])} | {f(v['macro_f1'])} | −{v['macro_f1_drop']:.3f} |"
            for k, v in nov["ablations"].items()))
        out[f"PERCAT_{tag.upper()}"] = "| Category | Correct | Accuracy |\n|---|---|---|\n" + "\n".join(
            f"| {c} | {v['correct']}/{v['total']} | {f(v['accuracy'])} |" for c, v in nov["full_pipeline_per_category"].items())
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--results", default=str(ROOT / "evaluation" / "results"))
    ap.add_argument("--colab", default=str(ROOT / "evaluation" / "colab_results"))
    ap.add_argument("--template", default=str(ROOT / "docs" / "report_nlp_template.md"))
    ap.add_argument("--out", default=str(ROOT / "docs" / "report_nlp_draft.md"))
    args = ap.parse_args()
    values = build(Path(args.results), Path(args.colab))
    text = Path(args.template).read_text()
    for k, v in values.items():
        text = text.replace("{{" + k + "}}", v)
    Path(args.out).write_text(text)
    missing = sorted({p.split("}}")[0] for p in text.split("{{")[1:]})
    print("wrote", args.out, "| missing:", missing or "none")


if __name__ == "__main__":
    main()
